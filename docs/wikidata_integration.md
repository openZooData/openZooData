# Wikidata Integration

OpenZooData uses Wikidata as its primary reference system for species and biodiversity-related information.

## Why Wikidata?

Building an open infrastructure for zoos requires stable, globally unique identifiers for animal species. Rather than inventing a new identifier system, OpenZooData reuses existing Wikidata entities.

Benefits include:

- Globally unique identifiers
- Multilingual labels
- Taxonomic hierarchy
- Conservation status information
- Interoperability with other open-data projects
- Long-term sustainability through a community-maintained knowledge graph

For example:

| Species | Wikidata ID |
|----------|------------|
| Lion | Q140 |
| Asian Elephant | Q677 |
| Red Panda | Q33602 |

These identifiers remain stable regardless of language or local naming conventions.

---

## How OpenZooData Uses Wikidata

Each species stored in OpenZooData contains a Wikidata reference.

Example:

```json
{
  "id": 38,
  "wikidata_id": "Q677",
  "common_name": "Asian Elephant",
  "scientific_name": "Elephas maximus"
}
```

The Wikidata identifier acts as the canonical reference for all related biodiversity information.

OpenZooData may use Wikidata to retrieve:

- Taxonomy
- Multilingual labels
- Conservation status
- Population trend information
- External identifiers
- Related Wikipedia articles
- Wikimedia Commons resources

---

## QR Codes and Open Standards

OpenZooData encourages the use of Wikidata identifiers in zoo signage and QR codes.

Example QR code payload:

```text
Q140
```

This approach is:

- Vendor-neutral
- Human-readable
- Future-proof
- Compatible with multiple applications

Any application that understands Wikidata identifiers can interpret the same QR code.

---

## Current Usage within OpenZooData

Today, Wikidata identifiers are used as the primary reference key for animal species.

Additional data sources may be linked through Wikidata, including:

- GBIF (Global Biodiversity Information Facility)
- IUCN Red List
- Wikimedia Commons
- Wikipedia
- Other biodiversity databases

This allows OpenZooData to connect multiple open datasets through a single shared identifier.

---

## Powered by Wikidata

OpenZooData proudly uses Wikidata as a foundational component of its open-data architecture.

Learn more about Wikidata:  

https://www.wikidata.org
