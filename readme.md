# Kagami
A discord bot made for use on small personal servers \
Probably has a lot of bugs that make it undesirable for large servers but has some fun features
## Hosting
### Local Hosting
- Lavalink Version [4.0.8](https://github.com/lavalink-devs/Lavalink/releases/tag/4.0.8)
  - The included [application config](./lavalink/application.yml) should suffice
### Building Docker Images
`docker build -f Dockerfile -t kagami_bot:amd64 .`

### Docker Compose

Just run `docker compose up -d` in the same directory as the compose.yaml files
- Lavalink should be hosted in a separate container from the bot but can be bundled using docker copose
  - Host networking should be enabled for proper interop
  

### Running Yourself
Create a venv for the project's requirements within the project directory \
`python -m venv .venv` \
Enter the venv \
Linux: `source .venv/bin/activate` \
Windows: `.venv/Scripts/activate.ps1` \
Now you can start the bot \
`python kagami/main.py`

This procedure assumes that you have just cloned the entire respository locally. \
By default the bot will attempt to run with music functionality which requires lavalink to be running in a seperate processes. 
If you do not want this then just remove the [music module](./kagami/cogs/depr_music.py) from the cogs directory. 
If you do not desire any other bit of functionality you can remove the corresponding module from the same directory. \
**Note:** Cog files are the only files that can be removed without breaking the bot. They contain various isolated feature sets that do no depend on eachother.

### Starting lavalink
Run the following command from the project source \
`python lavalink/lavalink.py` \
This does not need to be run within a virtual environment. \
The python scripts just serves to make it more convenient to start lavalink regardless of the host platform.
