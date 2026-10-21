# Vendored chart libraries

Served with the power page so it depends on no CDN. Both ISC-licensed (the
LICENSE files here). Fetched with `npm pack`, which checks each tarball
against the registry's integrity hash:

| File | Package | Registry integrity of the tarball |
|---|---|---|
| `d3-7.9.0.min.js` | `d3@7.9.0`, `dist/d3.min.js` | `sha512-e1U46jVP+w7Iut8Jt8ri1YsPOvFpg46k+K8TpCb0P+zjCkjkPnV7WzfDJzMHy1LnA+wj5pLT1wjO901gLXeEhA==` |
| `plot-0.6.16.umd.min.js` | `@observablehq/plot@0.6.16`, `dist/plot.umd.min.js` | `sha512-LRi9Rn93yUx90MIo2Md7+vazxO3Wiat14but2ttCER0xVS+jnfoUjuCGoz6H7bz/lgI9CFcW0HWlvWjMFjAv8g==` |

File SHA-256: `d3-7.9.0.min.js` f2094bbf6141b359722c4fe454eb6c4b0f0e42cc10cc7af921fc158fceb86539, `plot-0.6.16.umd.min.js` ee8e99124680704d3ea4878bdb786362c70a412b7b9eb988ae852827fd6e0711.

Plot's UMD build reads the global `d3`, so d3 loads first. To upgrade, `npm
pack` the new versions, copy the same two files, rename them, and update this
table and the two `<script>` tags in `site/power/index.html`.
