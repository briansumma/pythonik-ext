# Iconik Storage Gateway - Settings Impact Matrix

This matrix describes how various ISG (Iconik Storage Gateway) storage
settings affect asset registration, metadata handling, and folder
mapping behavior. Only implementation-relevant settings are included.

| Setting Name                           | Type    | Affects Logic In                                      | Outcome When True                                                             | Outcome When False                                                               |
| -------------------------------------- | ------- | ----------------------------------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| `enable_collection_directory_mapping`  | boolean | Directory-to-collection mapping                       | Each directory scanned becomes or maps to a Collection in iconik              | No collections created; assets are ungrouped or must be manually organized       |
| `filename_is_external_id`              | boolean | Asset identity / deduplication                        | Filename is used as `external_id` (asset deduplication is filename-based)     | External ID derived from full path, UUID, or other mechanism                     |
| `sidecar_metadata_required`            | boolean | Ingest validation, sidecar handling                   | File will not ingest unless sidecar exists and is valid                       | File can be ingested with or without sidecar                                     |
| `metadata_view_id`                     | UUID    | Metadata application                                  | Sidecar data applied to specified metadata view (via `/views/{view_id}/` API) | Sidecar ignored or fallback to generic/IPTC fields if compatible                 |
| `folder_name_tags_metadata_field_name` | string  | Metadata tagging                                      | Folder names in path stored as tags in metadata under this field              | No folder tags written                                                           |
| `folder_name_tags_metadata_view_id`    | UUID    | Metadata tagging (view-targeted)                      | Tags from folders written via metadata view API                               | Tags may be written directly via Admin-only API (or not at all if above not set) |
| `title_includes_extension`             | boolean | Asset naming                                          | Title of asset will include the file extension (e.g. `video.mov`)             | Title excludes extension (e.g. `video`)                                          |
| `acl_template_id`                      | UUID    | Asset permission template                             | Each new asset receives specified ACL template (overrides default)            | Asset inherits default or group-based permissions                                |
| `mount_point`                          | string  | Path normalization / directory_path / base_dir values | Used to calculate relative path used in file registration (see below)         | Without this, relative paths would be incorrect or undefined                     |
| `scan_include` / `scan_ignore`         | list    | File/directory filtering during scan                  | Only files matching include filters are scanned (include > ignore precedence) | All files scanned unless excluded by ignore pattern                              |

## Behavior Notes

- `mount_point`: Used to strip absolute paths to compute
  `directory_path` and `base_dir`.
- `scan_include` / `scan_ignore`: Accept both wildcard (`*.mov`) and
  regex (`re:/.../`). `scan_include` takes precedence.
- `sidecar_metadata_required` + `metadata_view_id`: `metadata_view_id`
  is required if sidecar is required. Without it, ingest fails even if
  sidecar exists.
- `folder_name_tags_metadata_view_id`: If omitted, fallback is
  Admin-only endpoint or tagging may not occur.
