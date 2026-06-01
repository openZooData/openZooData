# OpenZooData Licensing Overview

## 1. Server Software

License: GNU Affero General Public License v3.0 (AGPLv3)

The full license text is available in the LICENSE file and at:
https://www.gnu.org/licenses/agpl-3.0.txt

This means:
- You may use, modify, and distribute this software freely
- Any modified version you run as a public service must also be released under AGPLv3
- The source code must remain publicly accessible

## 2. Open Data

License: Open Database License (ODbL) v1.0
https://opendatacommons.org/licenses/odbl/1-0/

Applies to:
- Zoo datasets
- Species datasets
- Enclosure data
- Geographic data
- Public structured exports

This means:
- You may use, share, and adapt the data freely
- Adapted or derived databases must be released under ODbL
- Attribution to OpenZooData is required

## 3. Documentation

License: Creative Commons Attribution Share Alike 4.0 (CC BY-SA 4.0)
https://creativecommons.org/licenses/by-sa/4.0/

This means:
- You may share and adapt the documentation freely
- Attribution is required
- Adapted versions must use the same license

## 4. Trademarks

The following are NOT covered by the open source licenses:

- The name "OpenZooData"
- The OpenZooData logo and visual identity
- Official branding assets

Use of these assets requires explicit written permission.

## 5. Proprietary Components

The following systems are intentionally excluded from this repository
and may remain proprietary:

- ZooGuide iOS application
- ZooCreator data management tool
- Analytics infrastructure
- Commercial dashboards and integrations

## 6. Interoperability Requirements

Any implementation that uses OpenZooData data, APIs, or derived datasets
must comply with the following interoperability obligations:

### Data Availability

All zoo and species data served through an OpenZooData-compatible system
must remain freely accessible. Data must not be locked behind proprietary
access controls that prevent redistribution or reuse under ODbL terms.

### RSS Feed as Discovery Endpoint

Any OpenZooData-compatible server must expose a compliant RSS feed as the
primary public discovery endpoint. The RSS feed must:

- list all available zoo datasets
- reference current SQLite export URLs
- include data version information
- be publicly accessible without authentication

This ensures that data remains discoverable, federable, and accessible to
the open ecosystem regardless of the operator.

### Derived Implementations

Any system that modifies or extends OpenZooData server software and
operates as a public service must publish its source code under AGPLv3,
and must fulfill the RSS feed requirement above.
