# sites-infra

> Tuto complet (mise en place, quotidien, dépannage) : [DEPLOIEMENT.md](DEPLOIEMENT.md)

Déploiement de hugomeuriel.fr sur le serveur deva2 (192.168.11.134), derrière l'Apache de 192.168.11.131.

```
push sur main de hugomeuriel-portfolio ─► GitHub Actions : build + contrôles Django + test du conteneur
                                            ─► image ghcr.io/hug0003/hugomeuriel (:latest et :<sha>)
                                            │ événement « site-updated »
                                            ▼
                  sites-infra : workflow Deploy (VPN IKEv2 + SSH hugo-portfolio@.134)
                    copie docker-compose.yml, écrit env/*.env (secrets) → /opt/hugo-portfolio
                    docker compose pull + up -d, puis vérification de chaque chemin
Internet ─► .131 Apache (HTTPS, HSTS) ─► .134:8101 ─► UN conteneur : portfolio + /projets/<nom>/
```

**Un seul conteneur** (`hugomeuriel-site-1`) : Nginx y sert le portfolio et les projets statiques,
relaie l'API météo, et transmet crushbrito et pizzamama à deux gunicorn internes. Tout le code est dans
le repo **hugomeuriel-portfolio** ; les anciens repos des projets restent sur GitHub mais ne sont plus
déployés.

**Aucun code ni repo sur le serveur** : `/opt/hugo-portfolio` contient `docker-compose.yml`, `env/`
(secrets, lisibles par le conteneur seul) et `data/` (bases SQLite et images envoyées).

| Chemin | Source dans hugomeuriel-portfolio |
|---|---|
| `/` | racine (portfolio) |
| `/projets/guessmynumber/`, `icecream`, `natours`, `nexter`, `trillo`, `robot`, `sunorcloud` | `projets/<nom>/` |
| `/projets/crushbrito/`, `/projets/pizzamama/` | `apps/crushbrito/`, `apps/pizzamama/` (Django) |

Restent sur la Raspberry : photos.hugomeuriel.fr (Immich), Pi-hole, zabbix.

## Secrets GitHub

**Repo sites-infra** : `VPN_SERVER`, `VPN_USER`, `VPN_PASSWORD`, `SSH_HOST` (`192.168.11.134`),
`SSH_USER` (`hugo-portfolio`), `SSH_KEY`, `SSH_KNOWN_HOSTS`, `GHCR_TOKEN` (classic, `read:packages`),
`ENV_CRUSHBRITO`, `ENV_PIZZAMAMA` (`DJANGO_SECRET_KEY=…` / `DJANGO_ADMIN_PATH=…/`),
`ENV_SUNORCLOUD` (`OWM_API_KEY=…` / `OPENCAGE_API_KEY=…`).

**Repo hugomeuriel-portfolio** : `SITES_DEPLOY_TOKEN` (fine-grained, repo sites-infra, Contents: Read and write).

## Revenir en arrière

Remplacer `:latest` par `:<sha du commit>` dans `docker-compose.yml`, pousser (le workflow redéploie).
