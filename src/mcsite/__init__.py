"""The v2 storefront: reads the pipeline's own database, renders the pages.

Deliberately separate from `mcpipe`. The pipeline decides what is true; this
package only shows it. Nothing here writes to the database.
"""
