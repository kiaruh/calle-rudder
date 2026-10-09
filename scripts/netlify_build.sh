#!/bin/sh
# Netlify build: copy the static UI into dist/ and write the proxy rules to the backend.
# Static files win over the catch-all rule, so pages and the video come from Netlify's CDN,
# and everything else (/api/*, /calls/*, /crm/*, /docs, webhooks) is proxied to BACKEND_URL.
set -eu
BACKEND="${BACKEND_URL:-https://calle-rudder-api.onrender.com}"
BACKEND="${BACKEND%/}"
rm -rf dist
mkdir -p dist
cp -R app/orchestrator/static/. dist/
# Netlify ignores trailing slashes when matching rules, so "/crm" also matches "/crm/":
# proxy both straight to the backend's /crm/ (a "/crm -> /crm/" redirect here would loop forever).
cat > dist/_redirects <<EOF
/learn    /learn.html         200
/crm      ${BACKEND}/crm/     200
/*        ${BACKEND}/:splat   200
EOF
echo "Built dist/ (backend: ${BACKEND})"
