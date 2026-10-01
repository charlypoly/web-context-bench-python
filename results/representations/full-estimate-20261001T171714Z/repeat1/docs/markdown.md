Client.request() — Ferrite HTTP 3.2 documentation



Ferrite HTTP
Version

4.0 (beta)
3.2
3.1
2.9

[GitHub](#)
[Changelog](#)

### Getting started

* [Installation](#)
* [Quickstart](#)
* [Migrating from 2.x](#)

### API reference

* [Client](#)
* [Client.request()](#)
* [Client.stream()](#)
* [Response](#)
* [Timeout](#)
* [RetryPolicy](#)
* [Exceptions](#)

### Guides

* [Authentication](#)
* [Connection pooling](#)
* [Testing with mocks](#)


[Docs](#) / [API reference](#) / Client.request()

`Client.request()`
==================

Send an HTTP request and return a [`Response`](#). This is the low-level method that all verb helpers such as `client.get()` and `client.post()` call internally.

```
Copyresponse = client.request(
    method, url, *, params=None, headers=None, json=None,
    data=None, timeout=DEFAULT_TIMEOUT, follow_redirects=True,
    max_redirects=20, retry=None,
)
```

Parameters
----------

| Name | Type | Default | Description |
| --- | --- | --- | --- |
| `method` | `str` | required | HTTP method, for example `"GET"` or `"PATCH"`. Case-insensitive. |
| `url` | `str | URL` | required | Absolute URL, or a path relative to the client's `base_url`. |
| `params` | `dict | None` | `None` | Query string parameters. Lists are encoded as repeated keys. |
| `headers` | `dict | None` | `None` | Headers merged over the client's default headers. |
| `json` | `Any` | `None` | Body encoded as JSON. Sets `Content-Type: application/json`. Cannot be combined with `data`. |
| `timeout` | `float | Timeout` | `5.0` | Seconds to wait for the whole request. Pass a `Timeout` for separate connect and read limits. |
| `follow_redirects` | `bool` | `True` | Whether to follow 3xx responses automatically. |
| `max_redirects` | `int` | `20` | Raise `TooManyRedirects` after this many hops. |
| `retry` | `RetryPolicy | None` | `None` | Retry policy for idempotent methods. Non-idempotent methods are never retried. |

**Note:** Since version 3.0, `timeout` applies to the entire request rather than to each socket operation.

Returns
-------

A `Response` object. The body is read eagerly unless you use [`Client.stream()`](#).

Raises
------

* `ConnectTimeout` — the connection could not be established in time.
* `TooManyRedirects` — more than `max_redirects` redirects were followed.
* `InvalidURL` — the URL could not be parsed.

**Deprecated:** The `verify_ssl` argument was removed in 3.2. Configure TLS on the `Client` instead.

Example
-------

```
Copyfrom ferrite import Client, RetryPolicy

with Client(base_url="https://api.example.com") as client:
    response = client.request(
        "PATCH", "/orders/42",
        json={"status": "shipped"},
        retry=RetryPolicy(attempts=3),
    )
    response.raise_for_status()
```

[Edit this page](#) · Last updated on 2 February 2026

[← Previous: Client](#)
[Next: Client.stream() →](#)

Was this page helpful? Yes No


**On this page**

* [Parameters](#parameters)
* [Returns](#returns)
* [Raises](#raises)
* [Example](#example)