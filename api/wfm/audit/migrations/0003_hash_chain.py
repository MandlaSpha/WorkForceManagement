"""Tamper evidence for the audit trail (requirement AUD-10).

Every event carries `chain_seq`, `prev_hash` and `hash`, where

    hash = SHA-256( JSON array of the event's fields, including prev_hash and chain_seq )

and prev_hash is the previous event's hash. Editing, deleting or inserting a row anywhere breaks
the chain from that point on, so `audit_verify_chain()` finds it even when someone with database
superuser rights has switched the append-only triggers off.

The chain is extended by a BEFORE INSERT trigger under a transaction-level advisory lock: two
transactions must not both chain to the same predecessor. The order is `chain_seq`, assigned
under that lock, not the row id, because ids are allocated *before* the trigger runs. The lock
is held until commit, so `audit.record()` must be the last write in a transaction (see
wfm/audit/services.py).
"""

from django.db import migrations, models

DIGEST_FUNCTIONS = r"""
CREATE FUNCTION audit_event_digest(e audit_auditevent) RETURNS text AS $$
    SELECT encode(sha256(convert_to(jsonb_build_array(
        e.hash_version, e.chain_seq, e.prev_hash, e.id,
        to_char(e.occurred_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US'),
        e.actor_user_id, e.actor_role, e.actor_type, e.subject_employee_id,
        e.action, e.entity_type, e.entity_id, e.outcome, e.reason,
        e.request_id, e.trace_id, e.session_hash, host(e.ip), e.user_agent, e.batch_id
    )::text, 'UTF8')), 'hex')
$$ LANGUAGE sql STABLE;

CREATE FUNCTION audit_change_digest(c audit_auditchange, event_hash text) RETURNS text AS $$
    SELECT encode(sha256(convert_to(jsonb_build_array(
        c.id, c.event_id, c.entity_type, c.entity_id, c.field, c.old_value, c.new_value, event_hash
    )::text, 'UTF8')), 'hex')
$$ LANGUAGE sql STABLE;
"""

# Chain the rows that already exist (development databases), oldest first.
BACKFILL = r"""
ALTER TABLE audit_auditevent DISABLE TRIGGER audit_event_append_only;
ALTER TABLE audit_auditchange DISABLE TRIGGER audit_change_append_only;
DO $$
DECLARE
    r record;
    prev text := repeat('0', 64);
    seq bigint := 0;
    h text;
BEGIN
    FOR r IN SELECT id FROM audit_auditevent ORDER BY id LOOP
        seq := seq + 1;
        UPDATE audit_auditevent SET chain_seq = seq, prev_hash = prev, hash_version = 1 WHERE id = r.id;
        SELECT audit_event_digest(e) INTO h FROM audit_auditevent e WHERE e.id = r.id;
        UPDATE audit_auditevent SET hash = h WHERE id = r.id;
        prev := h;
    END LOOP;
    UPDATE audit_auditchange c
       SET hash = audit_change_digest(c, ev.hash)
      FROM audit_auditevent ev WHERE ev.id = c.event_id;
END $$;
ALTER TABLE audit_auditevent ENABLE TRIGGER audit_event_append_only;
ALTER TABLE audit_auditchange ENABLE TRIGGER audit_change_append_only;
"""

TRIGGERS = r"""
CREATE FUNCTION audit_event_chain() RETURNS trigger AS $$
DECLARE
    last_seq bigint;
    last_hash text;
BEGIN
    -- One chain, one writer at a time, until this transaction ends.
    PERFORM pg_advisory_xact_lock(7305001);
    SELECT chain_seq, hash INTO last_seq, last_hash
      FROM audit_auditevent ORDER BY chain_seq DESC LIMIT 1;
    NEW.chain_seq := COALESCE(last_seq, 0) + 1;
    NEW.prev_hash := COALESCE(last_hash, repeat('0', 64));
    NEW.hash_version := 1;
    NEW.hash := audit_event_digest(NEW);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_event_chain_insert
    BEFORE INSERT ON audit_auditevent
    FOR EACH ROW EXECUTE FUNCTION audit_event_chain();

CREATE FUNCTION audit_change_chain() RETURNS trigger AS $$
DECLARE
    event_hash text;
BEGIN
    SELECT hash INTO event_hash FROM audit_auditevent WHERE id = NEW.event_id;
    NEW.hash := audit_change_digest(NEW, event_hash);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_change_chain_insert
    BEFORE INSERT ON audit_auditchange
    FOR EACH ROW EXECUTE FUNCTION audit_change_chain();

-- Walks the chain in order and reports every place it does not hold.
CREATE FUNCTION audit_verify_chain() RETURNS TABLE(seq bigint, event_id bigint, problem text) AS $$
DECLARE
    e audit_auditevent;
    expected_prev text := repeat('0', 64);
    expected_seq bigint := 1;
BEGIN
    FOR e IN SELECT * FROM audit_auditevent ORDER BY chain_seq LOOP
        IF e.chain_seq <> expected_seq THEN
            RETURN QUERY SELECT e.chain_seq, e.id,
                format('sequence break: expected %s, found %s (an event was removed or inserted)',
                       expected_seq, e.chain_seq);
            expected_seq := e.chain_seq;
        END IF;
        IF e.prev_hash <> expected_prev THEN
            RETURN QUERY SELECT e.chain_seq, e.id,
                'prev_hash does not match the previous event'::text;
        END IF;
        IF e.hash <> audit_event_digest(e) THEN
            RETURN QUERY SELECT e.chain_seq, e.id,
                'event content does not match its hash (the row was altered)'::text;
        END IF;
        expected_prev := e.hash;
        expected_seq := expected_seq + 1;
    END LOOP;

    RETURN QUERY
        SELECT ev.chain_seq, c.event_id,
               'change row does not match its hash (the row was altered)'::text
          FROM audit_auditchange c
          JOIN audit_auditevent ev ON ev.id = c.event_id
         WHERE c.hash <> audit_change_digest(c, ev.hash);

    RETURN QUERY
        SELECT NULL::bigint, c.event_id, 'change row has no event'::text
          FROM audit_auditchange c
         WHERE NOT EXISTS (SELECT 1 FROM audit_auditevent ev WHERE ev.id = c.event_id);
END;
$$ LANGUAGE plpgsql STABLE;
"""

REVERSE = r"""
DROP FUNCTION audit_verify_chain();
DROP TRIGGER audit_change_chain_insert ON audit_auditchange;
DROP FUNCTION audit_change_chain();
DROP TRIGGER audit_event_chain_insert ON audit_auditevent;
DROP FUNCTION audit_event_chain();
DROP FUNCTION audit_change_digest(audit_auditchange, text);
DROP FUNCTION audit_event_digest(audit_auditevent);
"""


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_append_only")]

    operations = [
        migrations.AddField(
            model_name="auditevent",
            name="chain_seq",
            field=models.BigIntegerField(editable=False, null=True),
        ),
        migrations.AddField(
            model_name="auditevent",
            name="prev_hash",
            field=models.CharField(default="", editable=False, max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="auditevent",
            name="hash",
            field=models.CharField(default="", editable=False, max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="auditevent",
            name="hash_version",
            field=models.PositiveSmallIntegerField(default=1, editable=False),
        ),
        migrations.AddField(
            model_name="auditchange",
            name="hash",
            field=models.CharField(default="", editable=False, max_length=64),
            preserve_default=False,
        ),
        migrations.RunSQL(DIGEST_FUNCTIONS, migrations.RunSQL.noop),
        migrations.RunSQL(BACKFILL, migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="auditevent",
            name="chain_seq",
            field=models.BigIntegerField(editable=False, unique=True),
        ),
        migrations.RunSQL(TRIGGERS, REVERSE),
    ]
