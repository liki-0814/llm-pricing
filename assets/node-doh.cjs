/* Optional Node 18+ transport for networks with broken system DNS. No global changes. */
const https = require('node:https');
const net = require('node:net');

function createDohFetch(baseUrl, { resolverFetch = globalThis.fetch } = {}) {
  const base = new URL(baseUrl);
  if (base.protocol !== 'https:') throw new Error('DoH transport requires an HTTPS base URL');
  let cached;
  async function lookup(signal) {
    if (cached && cached.expires > Date.now()) return cached.addresses;
    const url = new URL('https://dns.google/resolve');
    url.searchParams.set('name', base.hostname);
    url.searchParams.set('type', 'A');
    const response = await resolverFetch(url, { signal });
    if (!response.ok) throw new Error('DNS-over-HTTPS HTTP ' + response.status);
    const answer = await response.json();
    const records = (answer.Answer || []).filter(r => r.type === 1 && net.isIP(r.data) === 4);
    if (answer.Status !== 0 || !records.length) throw new Error('DNS-over-HTTPS returned no IPv4 addresses');
    cached = {
      addresses: records.map(r => ({ address: r.data, family: 4 })),
      expires: Date.now() + Math.min(...records.map(r => Math.max(0, Number(r.TTL) || 0)), 3600) * 1000
    };
    return cached.addresses;
  }
  return async function dohFetch(url, { signal } = {}) {
    const target = new URL(url);
    if (target.origin !== base.origin) throw new Error('DoH transport is restricted to ' + base.origin);
    const addresses = await lookup(signal);
    signal?.throwIfAborted();
    return new Promise((resolve, reject) => {
      // Keep the original hostname for HTTP Host, SNI and certificate verification.
      const request = https.get(target, {
        signal,
        lookup: (_hostname, options, callback) => options.all
          ? callback(null, addresses)
          : callback(null, addresses[0].address, 4)
      }, response => {
        const chunks = [];
        response.on('error', reject);
        response.on('data', chunk => chunks.push(chunk));
        response.on('end', () => {
          const headers = new Headers();
          for (const [key, value] of Object.entries(response.headers))
            if (value !== undefined) headers.set(key, Array.isArray(value) ? value.join(', ') : value);
          resolve(new Response(Buffer.concat(chunks), { status: response.statusCode, headers }));
        });
      });
      request.on('error', reject);
    });
  };
}

module.exports = { createDohFetch };
