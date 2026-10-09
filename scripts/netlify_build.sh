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
cat > dist/_redirects <<EOF
/learn    /learn.html         200
/rudder   /rudder/            301
/crm      /crm/               301
/*        ${BACKEND}/:splat   200
EOF
echo "Built dist/ (backend: ${BACKEND})"
