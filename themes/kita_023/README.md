# Kita port for this blog

This is a local port of the pinned `themes/kita` submodule for Zola 0.23.6.
It retains Kita's MIT license and the templates and static assets used by this
site. Tera 1 macros, optional includes, removed filters, and older template
syntax were adapted for Tera 2. The old shortcode templates were omitted
because this blog does not use them and Zola 0.23 uses components instead.

The original submodule remains unchanged for attribution and reference. Keep
the Zola version in `.github/workflows/pages.yml` aligned with the local
version used for `zola build` and `zola serve --open`.
