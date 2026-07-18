#!/bin/sh
# Select a safe HTTP bootstrap config until Certbot has issued the domain
# certificate, then install the HTTPS-only public configuration on restart.
set -eu

domain="${DOMAIN:-brain.veriflowai.me}"
cert_dir="/etc/letsencrypt/live/${domain}"

if [ -f "${cert_dir}/fullchain.pem" ] && [ -f "${cert_dir}/privkey.pem" ]; then
    sed "s|__DOMAIN__|${domain}|g" \
        /etc/nginx/companybrain/nginx.docker.tls.conf.template \
        > /etc/nginx/conf.d/default.conf
    echo "Company Brain nginx: TLS configuration enabled for ${domain}."
else
    echo "Company Brain nginx: HTTP bootstrap mode (certificate for ${domain} is not present)."
fi
