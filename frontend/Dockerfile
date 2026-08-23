# syntax=docker/dockerfile:1.7
#
# Next.js frontend for headline_threads.
#
# bun.lock is the committed lockfile (package.json pins `packageManager:
# bun@1.3.13`), so the `deps` stage installs with Bun for reproducibility.
# However, Bun 1.3.13 crashes running `next build` on Render's build VM
# (segfault in the Turbopack page-data step, "Expected CommonJS module to
# have a function wrapper"), so `builder` and `runner` use Node 22 -- the
# runtime Next.js actually targets. Only installs run under Bun.
#
# NEXT_PUBLIC_API_URL must be present at build time -- Next inlines these
# variables into the compiled bundle -- so it is declared as a build arg and
# forwarded into the environment before `npm run build`.

FROM oven/bun:1.3.13-slim AS deps

WORKDIR /app

COPY package.json bun.lock ./
# --frozen-lockfile keeps builds reproducible; --ignore-scripts skips the
# `sharp` postinstall (see ignoreScripts in package.json).
RUN bun install --frozen-lockfile --ignore-scripts


FROM node:22-slim AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Baked into the client bundle. Provided per-environment by Render.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY . .

RUN npm run build


FROM node:22-slim AS runner

WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Non-root runtime.
RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

# Ship only what `next start` needs.
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json

USER nextjs

EXPOSE 3000

# Render injects $PORT. `next start -p $PORT` binds it correctly.
CMD ["sh", "-c", "exec ./node_modules/.bin/next start -H 0.0.0.0 -p ${PORT}"]
