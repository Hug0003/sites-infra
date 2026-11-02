# sites-infra

Hébergement de hugomeuriel.fr sur le serveur deva2 (192.168.11.134), derrière l'Apache de 192.168.11.131.

```
push sur main d'un site ─► GitHub Actions : build + contrôles ─► image sur ghcr.io/hug0003/site-<nom>
                                    │ événement « site-updated »
                                    ▼
                 sites-infra : workflow Deploy (VPN IKEv2 + SSH hugo-portfolio@.134)
                   copie docker-compose.yml, nginx/*.conf, env/*.env (secrets) → /opt/hugo-portfolio
                   docker compose pull + up -d, puis vérification de chaque site
Internet ─► .131 Apache (HTTPS, HSTS) ─► hugomeuriel.fr/ et hugomeuriel.fr/projets/<nom>/ ─► .134:81xx
```

**Aucun code ni repo sur le serveur** : `/opt/hugo-portfolio` ne contient que ce que le workflow y dépose
(compose, configs Nginx, fichiers .env) et les données des applis Django (`data/`).
Le jeton GHCR n'y reste pas : il sert le temps du `docker pull`, dans un dossier temporaire.

| Port | Chemin | Repo |
|---|---|---|
| 8101 | `/` | hugomeuriel-portfolio |
| 8102 | `/projets/guessmynumber/` | guess-my-number |
| 8103 | `/projets/icecream/` | glace |
| 8104 | `/projets/natours/` | travel |
| 8105 | `/projets/nexter/` | reservation-hotels |
| 8106 | `/projets/trillo/` | agence-de-voyage |
| 8107 | `/projets/robot/` | robot |
| 8108 | `/projets/sunorcloud/` | apiMeteo |
| 8111 | `/projets/crushbrito/` | crushbrito (Django) |
| 8112 | `/projets/pizzamama/` | Pizzeria (Django) |

Restent sur la Raspberry : photos.hugomeuriel.fr (Immich), Pi-hole, zabbix.

## Secrets GitHub

**Repo sites-infra** (Settings → Secrets and variables → Actions) :

| Secret | Valeur |
|---|---|
| `VPN_SERVER`, `VPN_USER`, `VPN_PASSWORD` | les mêmes que pour ICE-theaters (VPN du réseau de .134) |
| `SSH_HOST` | `192.168.11.134` |
| `SSH_USER` | `hugo-portfolio` |
| `SSH_KEY` | clé privée de déploiement (voir installation) |
| `SSH_KNOWN_HOSTS` | sortie de `ssh-keyscan -t ed25519 192.168.11.134` |
| `GHCR_TOKEN` | jeton GitHub *classic* avec uniquement `read:packages` |
| `ENV_CRUSHBRITO`, `ENV_PIZZAMAMA` | `DJANGO_SECRET_KEY=…` et `DJANGO_ADMIN_PATH=…/` (une ligne chacun) |
| `ENV_SUNORCLOUD` | `OWM_API_KEY=…` et `OPENCAGE_API_KEY=…` (nouvelles clés) |

**Chacun des 10 repos de site** : `SITES_DEPLOY_TOKEN`, un jeton *fine-grained* limité au repo
sites-infra avec la permission « Contents: Read and write » (nécessaire pour déclencher le déploiement).
Sans lui, l'image est publiée mais pas déployée (avertissement dans Actions).

## Sécurité en place

- **Conteneurs** : sans root, lecture seule, aucune capability, `no-new-privileges`, limites
  mémoire/processus, un réseau isolé par appli Django, projet compose `hugomeuriel` séparé de deva2.
- **Réseau** : ports 8101-8112 publiés sur 192.168.11.134 seulement (pas d'exposition Internet ;
  joignables depuis le réseau local et le VPN, en plus de l'Apache de .131).
- **Navigateur** : CSP par site, HSTS, nosniff, X-Frame-Options, Referrer-Policy, Permissions-Policy, SRI.
- **Météo** : clés d'API ajoutées par Nginx côté serveur, 30 requêtes/min par visiteur.
- **Django** : DEBUG off, SECRET_KEY obligatoire, cookies sécurisés, CSRF sur les suppressions,
  admin à une adresse secrète, connexion limitée à 10 essais/min, médias jamais exécutés.
- **CI** : `manage.py check --deploy` bloque une config Django non sûre ; Dependabot hebdomadaire ;
  déploiement vérifié site par site (le workflow échoue si l'un ne répond pas).

## Fuites à traiter (historique Git public)

- Clés OpenWeatherMap et OpenCage : à révoquer, nouvelles clés dans `ENV_SUNORCLOUD`.
- SECRET_KEY Django : ne jamais réutiliser les anciennes.
- `db.sqlite3` de crushbrito et Pizzeria (comptes, e-mails, téléphones) : `git filter-repo` +
  `git push --force`, ou passer ces deux repos en privé.

## Revenir en arrière

Chaque image est aussi taguée avec le SHA du commit : remplacer `:latest` par `:<sha>` pour le site
concerné dans `docker-compose.yml`, puis pousser (le workflow redéploie).
