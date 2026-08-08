# Tiny Minds Example HTTP Provider

This separately packaged example shows how an external extension can provide embedding, reranking, natural-language inference, and zero-shot classification operations to Tiny Minds over HTTP.

It is an integration example, not a hosted production service. The accompanying deterministic fake server exists for sterile acceptance tests and development smoke checks.

Install it alongside the matching Tiny Minds release:

```powershell
python -m pip install tiny-minds==0.2.0
python -m pip install .\tiny_minds_example_http_provider-0.2.0-py3-none-any.whl
```

The package registers the `example-http` entry point in the `tiny_minds.providers` group. Provider endpoints, model identities, authentication references, timeouts, and batch limits remain host-configured.

Licensed under Apache-2.0 as part of the Tiny Minds repository.
