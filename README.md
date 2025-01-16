# Use `aiohttp` with `httpx` Interface

`httpx` has performance issue, especially when working with high concurrency, while `aiohttp` does not.

However, your production code and tests may already heavily rely on `httpx`, making it difficult to migrate to
`aiohttp`.

This repo provides a workaround: take advantage of `httpx`'s custom transport capability to use `aiohttp` for the actual
requests

This package supports:

- transport limits (max connection)
- auth
- proxy
- `respx`

Known limitations:

- http2. `aiohttp` does not support http2.
