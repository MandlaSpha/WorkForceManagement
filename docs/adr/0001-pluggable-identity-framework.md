# ADR 0001: A thin pluggable identity framework on Authlib and ldap3

Status: Accepted, 13 October 2026

## Context
Gijima is a Microsoft shop (Entra ID, probably on-prem AD too); the UIF tender customer is a public body that may run on-prem AD or LDAP; later customers will use Okta, Keycloak or Google. The requirement is to "plug in all the integrations companies usually use" without rewriting sign-in each time (AUTH-01).

## Options considered
1. **django-allauth.** Mature, many providers, SAML. But it owns the sign-in views, user model flows and templates; its headless API would sit beside our own audit trail, role scoping and CSRF/session rules, and it has no LDAP. Bending it to audit every outcome in the same transaction (AUD-08) and map groups to our six roles is as much work as writing the thin layer.
2. **django-auth-ldap + mozilla-django-oidc as authentication backends.** Fine individually, but each decides on its own how users are created and linked, so group-to-role mapping, provisioning policy and auditing end up duplicated or inconsistent.
3. **A thin framework of our own** (chosen): one `IdentityProvider` interface, one shared "complete sign-in" service for linking, provisioning, role mapping and auditing, and adapters built on well-reviewed libraries (Authlib for OIDC token validation, ldap3 for LDAP).

## Decision
Option 3. Adapters only translate a foreign login into a neutral `ExternalIdentity`; everything that matters for security and accountability happens once, in the shared service. Provider configuration is code, not a database table, until an admin screen is justified, so secrets never enter the database.

## Consequences
- Adding SAML, SCIM or another directory is a new adapter, not a change to users, roles or audit.
- We own the glue code and its tests (AUTH-15), including the security checks listed in AUTH-07 to AUTH-09.
- Licences: Authlib BSD-3, ldap3 LGPL-3.0 (on our allow-list: runtime-linked, unmodified), responses Apache-2.0 (tests only).
- SAML needs native XML-signature libraries (xmlsec) that are awkward on Windows developer machines; it stays an extension point until a customer requires it.
