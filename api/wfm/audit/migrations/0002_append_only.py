"""Make the audit tables append-only inside the database (requirement AUD-09).

The application role can still INSERT and SELECT; UPDATE, DELETE and TRUNCATE raise, even for
the table owner. Production additionally revokes UPDATE/DELETE/TRUNCATE from the app role.
"""

from django.db import migrations

FORWARD = """
CREATE FUNCTION audit_block_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'audit tables are append-only (% on %)', TG_OP, TG_TABLE_NAME
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_append_only
    BEFORE UPDATE OR DELETE ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_block_mutation();
CREATE TRIGGER audit_event_no_truncate
    BEFORE TRUNCATE ON audit_auditevent
    FOR EACH STATEMENT EXECUTE FUNCTION audit_block_mutation();

CREATE TRIGGER audit_change_append_only
    BEFORE UPDATE OR DELETE ON audit_auditchange
    FOR EACH ROW EXECUTE FUNCTION audit_block_mutation();
CREATE TRIGGER audit_change_no_truncate
    BEFORE TRUNCATE ON audit_auditchange
    FOR EACH STATEMENT EXECUTE FUNCTION audit_block_mutation();
"""

REVERSE = """
DROP TRIGGER audit_change_no_truncate ON audit_auditchange;
DROP TRIGGER audit_change_append_only ON audit_auditchange;
DROP TRIGGER audit_event_no_truncate ON audit_auditevent;
DROP TRIGGER audit_event_append_only ON audit_auditevent;
DROP FUNCTION audit_block_mutation();
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
