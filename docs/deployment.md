# Deployment Overview

## Current Runtime Model

The OpenZooData server is designed to run behind:

- nginx
- Apache reverse proxy

## Environment Variables

Required configuration includes:

- PostgreSQL credentials (zoo database)
- Auth database credentials
- JWT secrets
- Health check key

## Security Measures

Current implementation includes:

- JWT validation
- device token hashing
- rate limiting
- slug validation
- path traversal protection
- reverse proxy header support

## Recommended Production Setup

- HTTPS only
- reverse proxy
- separated analytics services
- separated authentication services
- automated backups
- CI/CD pipeline
