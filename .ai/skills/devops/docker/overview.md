# Docker Overview

Docker builds an image from a `Dockerfile` and runs it as an isolated
container. The two things most task-scoped changes get wrong are image
size/build time (from unnecessary layers or a bad `COPY`/dependency-install
order) and running production containers as root with a mutable `latest`
base image. Check the project's existing `Dockerfile`(s) and
`docker-compose.yml` for its base-image and multi-stage conventions before
changing them — don't introduce a second build style alongside an existing
one.
