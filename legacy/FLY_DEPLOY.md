## Fly Deploy

Deploy the main app:

```bash
./scripts/deploy_main_app.sh
```

Deploy the Reddit poller:

```bash
./scripts/deploy_reddit_poller.sh
```

Set machine count explicitly (including scaling to zero):

```bash
MACHINE_COUNT=0 ./scripts/deploy_main_app.sh
MACHINE_COUNT=0 ./scripts/deploy_reddit_poller.sh
```

Direct Fly CLI equivalents:

```bash
fly scale count 0 -a burning-man-matchbot --yes
fly scale count 0 --process-group poller -a burning-man-matchbot-reddit-poller --yes
```
