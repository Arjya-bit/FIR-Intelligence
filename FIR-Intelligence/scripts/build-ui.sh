#!/usr/bin/env bash
# Compile static/app.jsx -> static/app.js and refresh static/vendor/.
#
# The dashboard ships precompiled so the browser never has to download or run
# Babel (~2.9 MB) on every page load, and vendored so it works on an isolated
# network with no CDN access.
set -euo pipefail
cd "$(dirname "$0")/.."

npm install --no-audit --no-fund --no-save \
  react@18.3.1 react-dom@18.3.1 recharts@2.15.3 prop-types@15.8.1 \
  react-is@18.3.1 @babel/core@7.26.0 @babel/cli@7.25.9 @babel/preset-react@7.25.9

npx babel static/app.jsx --presets @babel/preset-react --out-file static/app.js

cp node_modules/react/umd/react.production.min.js         static/vendor/react.min.js
cp node_modules/react-dom/umd/react-dom.production.min.js static/vendor/react-dom.min.js
cp node_modules/prop-types/prop-types.min.js              static/vendor/prop-types.min.js
cp node_modules/react-is/umd/react-is.production.min.js   static/vendor/react-is.min.js
cp node_modules/recharts/umd/Recharts.js                  static/vendor/recharts.min.js

echo "Rebuilt static/app.js and static/vendor/"
