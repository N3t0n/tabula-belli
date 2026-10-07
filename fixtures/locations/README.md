# Fixed European location catalogue

Version: 2026-10-06. Source: [GeoNames](https://www.geonames.org/), distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). This is a filtered and converted extract, not a complete copy of GeoNames.

The three public source files were downloaded on 2026-10-06. `manifest.json` records their URLs, server modification dates, SHA-256 hashes, the application's country filter and the resulting fixture hash. The catalogue contains 43 countries, 948 regions and 57,945 populated places with population >= 1,000. All city coordinates and foreign-key references were validated. The current importer does not populate subregions.

The gzip-compressed Django fixture contains only location reference data. It contains no application users, events, registrations, credentials or Site configuration. Keep this dated file immutable: an update should produce a new version and manifest.

## Build a new empty database

Use the project's pinned Python dependencies and a dedicated PostgreSQL database. Set the normal application environment variables for that database, then run from the repository root:

```sh
python src/manage.py migrate --noinput
python src/manage.py loaddata fixtures/locations/europe-2026-10-06.json.gz
```

Then seed games, users, events and registrations using the existing commands, or use `reset_demo --confirm` with its explicit disposable-database and private-admin settings. Configure the Django Site separately for the deployment domain.

Loading this fixture requires no GeoNames download. Check the fixture SHA-256 against `manifest.json` before using it. Do not load it on top of an existing location catalogue: fixture primary keys belong to this export and can conflict with existing event/profile references. Migrating a running deployment to a new catalogue must be treated separately, using stable GeoNames identifiers and checked relations.

## Periodic demo renewal

The existing `reset_demo` command preserves locations and the Django Site. It rebuilds games, demo users, events with relative dates, registrations and the private administrator. It requires `DEMO_RESET_ALLOWED`, the exact `DEMO_RESET_DATABASE_NAME`, `DEMO_ADMIN_USERNAME`, `DEMO_ADMIN_EMAIL`, `DEMO_ADMIN_PASSWORD`, and explicit `--confirm`.

Keep real admin credentials outside Git. This work does not activate a production reset job or create periodic backups.

## Refresh the catalogue deliberately

`load_cities` remains the import tool for GeoNames. Run it on a separate empty database against freshly downloaded source files, validate seed references and relationships, export location tables with Django `dumpdata`, and record a new manifest. Do not use changing live downloads during routine reconstruction or scheduled demo resets.
