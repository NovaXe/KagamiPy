# Kagami
A discord bot made for use on small personal servers \
Probably has a lot of bugs that make it undesirable for large servers but has some fun features
## Hosting Requirements
### Local Hosting
- Lavalink Version [3.7.11](https://github.com/lavalink-devs/Lavalink/releases/tag/3.7.11)
  - The include [application config](./lavalink/application.yml) should suffice
### Docker
- Can just run `docker compose up -d` in the same directory as the compose.yaml files
- Lavalink should be hosted in a seperate container from the bot but can be bundled using docker copose
  - Host networking should be enabled for proper interop
