// Local development orchestration for Gijima WFM (tech spec section 9).
// Aspire only starts and wires the services; no production code depends on it.
// CI and hosted environments run the same container images without Aspire.

var builder = DistributedApplication.CreateBuilder(args);

const string apiDir = "../../../api";

var postgres = builder.AddPostgres("postgres").WithDataVolume("wfm-pgdata");
var db = postgres.AddDatabase("wfm");
var valkey = builder.AddValkey("valkey");

// One-off: apply database migrations before anything else starts.
var migrate = builder.AddPythonApp("migrate", apiDir, "manage.py")
    .WithUv()
    .WithArgs("migrate", "--noinput")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WaitFor(db);

var api = builder.AddPythonApp("api", apiDir, "manage.py")
    .WithUv()
    .WithArgs("runserver", "127.0.0.1:8000", "--noreload")
    .WithHttpEndpoint(port: 8000, targetPort: 8000, name: "http", isProxied: false)
    .WithHttpHealthCheck("/readyz")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WaitForCompletion(migrate)
    .WaitFor(valkey);

// Windows has no prefork pool, so the dev worker uses the solo pool.
builder.AddPythonExecutable("worker", apiDir, "celery")
    .WithUv()
    .WithArgs("-A", "config", "worker", "-l", "info", "-P", "solo")
    .WithEnvironment("DATABASE_URL", db.Resource.UriExpression)
    .WithEnvironment("WFM_BROKER_URL", valkey.Resource.UriExpression)
    .WaitForCompletion(migrate)
    .WaitFor(valkey);

builder.Build().Run();
