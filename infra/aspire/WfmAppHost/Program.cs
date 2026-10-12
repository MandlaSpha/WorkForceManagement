// Local development orchestration for Gijima WFM (tech spec section 9).
// Aspire only starts and wires the services; no production code depends on it.
// CI and hosted environments run the same container images without Aspire.

var builder = DistributedApplication.CreateBuilder(args);

const string apiDir = "../../../api";
const string webDir = "../../../web";

var postgres = builder.AddPostgres("postgres").WithDataVolume("wfm-pgdata");
var db = postgres.AddDatabase("wfm");
var valkey = builder.AddValkey("valkey");

// Password for the synthetic demo accounts: generated once and kept in user secrets, so no
// password is ever written into the repository.
var demoPassword = builder.AddParameter(
    "demo-password",
    new GenerateParameterDefault { MinLength = 16, Special = false },
    secret: true,
    persist: true);

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

var api = builder.AddPythonApp("api", apiDir, "manage.py")
    .WithUv()
    .WithArgs("runserver", "127.0.0.1:8000", "--noreload")
    .WithHttpEndpoint(port: 8000, targetPort: 8000, name: "http", isProxied: false)
    .WithHttpHealthCheck("/readyz")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WaitForCompletion(seed)
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
