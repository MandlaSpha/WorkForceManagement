// Local development orchestration for Gijima WFM (tech spec section 9).
// Aspire only starts and wires the services; no production code depends on it.
// CI and hosted environments run the same container images without Aspire.

var builder = DistributedApplication.CreateBuilder(args);

const string apiDir = "../../../api";
const string webDir = "../../../web";

// pgAdmin 4 (open source, PostgreSQL licence) is a development-only data browser. Aspire connects
// it to the database automatically, so there is nothing to type in; the fixed port keeps the URL
// the same between runs.
var postgres = builder
    .AddPostgres("postgres")
    .WithDataVolume("wfm-pgdata")
    .WithPgAdmin(pgAdmin => pgAdmin.WithHostPort(5050));
var db = postgres.AddDatabase("wfm");
var valkey = builder.AddValkey("valkey");

// Password for the synthetic demo accounts: generated once and kept in user secrets, so no
// password is ever written into the repository.
var demoPassword = builder.AddParameter(
    "demo-password",
    new GenerateParameterDefault { MinLength = 16, Special = false },
    secret: true,
    persist: true);

// A real LDAP directory for development, so directory sign-in is exercised end to end. It holds
// synthetic people only (see `manage.py seed_demo_directory`). The admin password is generated
// and kept in user secrets like the demo password.
var ldapAdminPassword = builder.AddParameter(
    "ldap-admin-password",
    new GenerateParameterDefault { MinLength = 16, Special = false },
    secret: true,
    persist: true);

var ldap = builder.AddContainer("openldap", "osixia/openldap", "1.5.0")
    .WithEnvironment("LDAP_ORGANISATION", "Example")
    .WithEnvironment("LDAP_DOMAIN", "example.org")
    .WithEnvironment("LDAP_ADMIN_PASSWORD", ldapAdminPassword)
    .WithEnvironment("LDAP_TLS", "false")
    .WithEndpoint(port: 3890, targetPort: 389, name: "ldap", isProxied: false);

// Identity providers offered on the login page (requirement AUTH-01..03). No secret appears
// here: the directory provider names the environment variable that holds its bind password.
const string identityProviders = """
[
  {
    "kind": "ldap",
    "key": "corp",
    "label": "Company directory",
    "server_uri": "ldap://localhost:3890",
    "allow_insecure": true,
    "bind_dn": "cn=admin,dc=example,dc=org",
    "bind_password_env": "LDAP_BIND_PASSWORD",
    "user_search_base": "ou=people,dc=example,dc=org",
    "user_filter": "(uid={username})",
    "subject_attribute": "entryUUID",
    "username_attribute": "uid",
    "group_base": "ou=groups,dc=example,dc=org",
    "group_format": "cn",
    "groups_from_member_of": false,
    "provisioning": {
      "mode": "auto",
      "trust_attributes": true,
      "role_rules": [
        { "group": "WFM Admins", "role": "admin" },
        { "group": "WFM Planners", "role": "planner" },
        { "group": "WFM Leads", "role": "lead" },
        { "group": "WFM Agents", "role": "agent" }
      ]
    }
  }
]
""";

// One-off: apply database migrations before anything else starts.
var migrate = builder.AddPythonApp("migrate", apiDir, "manage.py")
    .WithUv()
    .WithArgs("migrate", "--noinput")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WaitFor(db);

// One-off: create the synthetic demo logins (development settings only; the command refuses to
// run elsewhere). It is idempotent, so it is safe on every start.
var seed = builder.AddPythonApp("seed-demo", apiDir, "manage.py")
    .WithUv()
    .WithArgs("seed_demo", "--reset-passwords")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_DEMO_PASSWORD", demoPassword)
    .WaitForCompletion(migrate);

// One-off: put the synthetic people and groups into the directory (waits for it to start).
var seedDirectory = builder.AddPythonApp("seed-directory", apiDir, "manage.py")
    .WithUv()
    .WithArgs("seed_demo_directory")
    .WithEnvironment("LDAP_URI", "ldap://localhost:3890")
    .WithEnvironment("LDAP_ADMIN_PASSWORD", ldapAdminPassword)
    .WithEnvironment("WFM_DEMO_PASSWORD", demoPassword)
    .WaitFor(ldap);

// On demand (press Start in the dashboard): delete the synthetic data the browser tests import
// into the "E2E Queue". Never touches another queue; the command refuses outside development.
builder.AddPythonApp("purge-e2e-data", apiDir, "manage.py")
    .WithUv()
    .WithArgs("purge_e2e_data")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WaitForCompletion(migrate)
    .WithExplicitStart();

// On demand (press Start in the dashboard): fill the database with an invented, believable
// contact centre (history, staff, forecasts, rosters, leave, tickets) for demonstrations. It
// refuses outside development and when the demo data is already there.
builder.AddPythonApp("seed-demo-data", apiDir, "manage.py")
    .WithUv()
    .WithArgs("seed_demo_data")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WaitForCompletion(seed)
    .WithExplicitStart();

var api = builder.AddPythonApp("api", apiDir, "manage.py")
    .WithUv()
    .WithArgs("runserver", "127.0.0.1:8000", "--noreload")
    .WithHttpEndpoint(port: 8000, targetPort: 8000, name: "http", isProxied: false)
    .WithHttpHealthCheck("/readyz")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WithEnvironment("WFM_IDENTITY_PROVIDERS", identityProviders)
    .WithEnvironment("LDAP_BIND_PASSWORD", ldapAdminPassword)
    .WaitForCompletion(seed)
    .WaitForCompletion(seedDirectory)
    .WaitFor(valkey);

// Windows has no prefork pool, so the dev worker uses the solo pool.
builder.AddPythonExecutable("worker", apiDir, "celery")
    .WithUv()
    .WithArgs("-A", "config", "worker", "-l", "info", "-P", "solo")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WaitForCompletion(migrate)
    .WaitFor(valkey);

// The Vue app. Vite proxies /api to the Django API so cookies stay same-origin.
// The scheduler: runs the nightly audit hash-chain check (CELERY_BEAT_SCHEDULE in settings).
builder.AddPythonExecutable("beat", apiDir, "celery")
    .WithUv()
    .WithArgs("-A", "config", "beat", "-l", "info")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WaitForCompletion(migrate)
    .WaitFor(valkey);

// Browser spans go to /otlp on the web origin; Vite forwards them to the dashboard's OTLP/HTTP
// port, so telemetry stays inside our own infrastructure and needs no CORS.
var otlpHttp = builder.Configuration["ASPIRE_DASHBOARD_OTLP_HTTP_ENDPOINT_URL"]
    ?? "http://localhost:19889";

builder.AddViteApp("web", webDir)
    .WithPnpm()
    .WithEnvironment("API_URL", api.GetEndpoint("http"))
    .WithEnvironment("OTLP_HTTP_URL", otlpHttp)
    .WithEnvironment("VITE_OTEL_ENABLED", "1")
    .WithEnvironment("VITE_DEMO_LOGINS", "1")
    .WithEnvironment("VITE_DEMO_PASSWORD", demoPassword)
    .WaitFor(api);

builder.Build().Run();
