# Docker Examples

**Multi-stage Node.js build (slim, non-root final image):**
```dockerfile
FROM node:20.11-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20.11-alpine
WORKDIR /app
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
COPY package*.json ./
USER app
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3000/health || exit 1
ENTRYPOINT ["node"]
CMD ["dist/index.js"]
```

**`.dockerignore` matching the project's `.gitignore`:**
```
.git
node_modules
dist
.env
.env.*
!.env.example
*.log
```

Before writing a new `Dockerfile` or `docker-compose.yml` service, find an
existing service in the project with a similar runtime (same language,
similar dependency footprint) and match its base-image version, user
setup, and healthcheck convention rather than introducing a new style.
