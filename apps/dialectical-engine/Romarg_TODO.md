# Romarg TODO For dezbatere.ro

Goal: delegate `dezbatere.ro` from Romarg DNS to Cloudflare DNS so this Mac can host the app through Cloudflare Tunnel.

Do not copy personal contact details from the Romarg page into project files or screenshots.

## Before Changing Anything

- Wait until `Cloudfare_TODO.md` step 1 gives you the two exact Cloudflare nameservers for `dezbatere.ro`.
- Do not guess Cloudflare nameservers. They are assigned per zone and must match what Cloudflare shows.
- In Romarg, take a screenshot or note of the current nameservers before changing them.
- Check whether `dezbatere.ro` currently has any DNS records you care about at Romarg:
  - website records,
  - email/MX records,
  - TXT records for verification,
  - any subdomains.
- If there are records you care about, add them in Cloudflare before changing Romarg nameservers.
- Optional: after Cloudflare shows the two nameservers, run
  `CLOUDFLARE_NAMESERVERS="first.ns.cloudflare.com second.ns.cloudflare.com" make prepare-romarg-nameservers`
  with the real values. Then use `Romarg_Nameservers_To_Set.md` as a paste
  card for the form.

## Change Nameservers In Romarg

From the page shown in your screenshot:

1. Open the `Dezbatere.ro` domain details page in Romarg.
2. In `Unelte disponibile`, click `Modificare nameservere`.
3. Replace the current Romarg nameservers with the two Cloudflare nameservers shown in Cloudflare.
4. Remove every Romarg nameserver from the form. The final saved list should contain only Cloudflare nameservers.
5. Leave extra nameserver fields blank unless Cloudflare gives more than two.
6. Save/confirm the change.
7. If Romarg asks for confirmation by email or domain authorization, complete that confirmation.

## Expected Result

After saving, DNS delegation should eventually show Cloudflare nameservers:

```sh
dig +short dezbatere.ro NS
```

You can also run this from the project directory to wait for ROTLD to see the
new nameservers:

```sh
make hosting-status
make wait-dezbatere-dns
```

When that succeeds, continue with:

```sh
cloudflared tunnel login
make resume-dezbatere-hosting
```

Expected shape:

```text
<name>.ns.cloudflare.com.
<name>.ns.cloudflare.com.
```

Propagation can be quick, but allow up to 24 hours before assuming it failed.

## Do Not Do This

- Do not set `A` records to your home IP for this setup.
- Do not use Romarg hosting or cPanel for this app.
- Do not change DNSSEC unless Cloudflare/Romarg shows DNSSEC is enabled and blocking activation.
- Do not remove useful email records unless they have already been copied into Cloudflare.

## Status

- Current observed registrar: Romarg.
- Current observed nameservers: Romarg nameservers.
- DNSSEC observed inactive.
- Current public DNS problem: the `.ro` registry delegates `dezbatere.ro` to
  Romarg nameservers, but Romarg authoritative DNS currently returns `REFUSED`
  for the zone, which causes public resolvers to return `SERVFAIL`.
- Next action: complete `Cloudfare_TODO.md` step 1, then return here with the two Cloudflare nameservers.
