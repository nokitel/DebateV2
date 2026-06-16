# Romarg Nameservers To Set

Generated at: `2026-05-28T01:00:41.702200+00:00`
Status: waiting for Cloudflare-assigned nameservers.

After adding `dezbatere.ro` to Cloudflare, run:

```sh
CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers
```

Replace the example names with the exact two nameservers Cloudflare shows for this zone.
