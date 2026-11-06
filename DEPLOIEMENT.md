# Déploiement automatique de hugomeuriel.fr

Tuto complet : comment le portfolio et les projets sont déployés, comment tout mettre en place depuis zéro,
et quoi faire quand ça casse. Même principe que deva2.fr (VPN Freebox + SSH vers .134).

---

## 1. Vue d'ensemble

```
git push sur main de github.com/Hug0003/hugomeuriel-portfolio
  │
  ├─ GitHub Actions — deploy.yml :
  │     construit l'image unique (portfolio + tous les projets)
  │     contrôles Django (check --deploy, migrations) de crushbrito et pizzamama
  │     lance le conteneur comme en production et vérifie chaque chemin, les fichiers interdits et les CSP
  │     publie ghcr.io/hug0003/hugomeuriel (:latest et :<sha>)
  │     prévient sites-infra (événement « site-updated », secret SITES_DEPLOY_TOKEN)
  ▼
GitHub Actions de sites-infra — deploy.yml :
  │     connexion au VPN de la Freebox (IKEv2)
  │     SSH hugo-portfolio@192.168.11.134 → copie docker-compose.yml + écrit env/*.env
  │     docker compose pull + up -d
  │     vérifie que le portfolio et chaque projet répondent, sinon le déploiement échoue
  ▼
Visiteur → https://hugomeuriel.fr                 → portfolio
           https://hugomeuriel.fr/projets/<nom>/  → chaque projet
  → serveur main 192.168.11.131 (Apache, reverse proxy + certificat Let's Encrypt)
  → serveur deva2 192.168.11.134:8101 → UN conteneur « hugomeuriel-site-1 »
```

**Un seul conteneur.** À l'intérieur, Nginx sert le portfolio et les projets statiques, relaie l'API météo
(les clés restent sur le serveur), et transmet `/projets/crushbrito/` et `/projets/pizzamama/` à deux
gunicorn internes (127.0.0.1:8001 et 8002).

**Un seul repo de code : hugomeuriel-portfolio.** Les anciens repos des projets (guess-my-number, glace,
travel, reservation-hotels, agence-de-voyage, robot, apiMeteo, crushbrito, Pizzeria) restent sur GitHub
mais **ne sont plus déployés** : toute modification se fait dans hugomeuriel-portfolio.

**Rien n'est cloné sur le serveur** : `/opt/hugo-portfolio` contient `docker-compose.yml`, `env/`
(secrets) et `data/` (bases SQLite et images envoyées des applis Django).

### Où est quoi

| URL | Dans hugomeuriel-portfolio | Type |
|---|---|---|
| `/` | racine | portfolio |
| `/projets/guessmynumber/` | `projets/guessmynumber/` | statique |
| `/projets/icecream/` | `projets/icecream/` | statique |
| `/projets/natours/` | `projets/natours/` | statique |
| `/projets/nexter/` | `projets/nexter/` | statique |
| `/projets/trillo/` | `projets/trillo/` | statique |
| `/projets/robot/` | `projets/robot/` | statique |
| `/projets/sunorcloud/` | `projets/sunorcloud/` | statique + relais API météo |
| `/projets/crushbrito/` | `apps/crushbrito/` | Django |
| `/projets/pizzamama/` | `apps/pizzamama/` | Django |

| Fichier | Rôle |
|---|---|
| `hugomeuriel-portfolio/Dockerfile` | L'image unique : Python + Nginx, statiques Django collectés au build. |
| `hugomeuriel-portfolio/docker/nginx.conf.template` | Tous les chemins, le relais météo, la limitation de débit. |
| `hugomeuriel-portfolio/docker/headers/*.conf` | En-têtes de sécurité, une CSP par projet. |
| `hugomeuriel-portfolio/docker/start.sh` | Démarre les 2 gunicorn et Nginx ; si l'un tombe, le conteneur redémarre. |
| `hugomeuriel-portfolio/.github/workflows/deploy.yml` | Build, contrôles, test du conteneur, publication, déclenchement du déploiement. |
| `sites-infra/.github/workflows/deploy.yml` | VPN → SSH → compose + secrets → `docker compose up` → vérification. |
| `sites-infra/docker-compose.yml` | Le conteneur unique (port 8101, lecture seule, sans privilèges). |
| `sites-infra/apache/hugomeuriel-sites.conf` | Vhost Apache de .131. |
| `sites-infra/env/*.env.example` | Modèles **vides**. Les vraies valeurs sont uniquement dans les secrets GitHub. |

### Quand est-ce que ça se déclenche ?

| Événement | Image | Déploiement |
|---|---|---|
| Pull request vers main de hugomeuriel-portfolio | construite et testée, pas publiée | — |
| Push / merge sur main de hugomeuriel-portfolio | construite, testée, publiée | ✅ |
| Push sur main de sites-infra | — | ✅ |
| sites-infra → Actions → Deploy (VPN) → Run workflow | — | ✅ |

---

## 2. Mise en place depuis zéro

À faire **une seule fois**. Ensuite, chaque push sur `main` de hugomeuriel-portfolio déploie tout seul.

### Étape 1 — Serveur deva2 (192.168.11.134)

En root sur .134 :

```bash
docker --version && docker compose version
id hugo-portfolio || useradd -m -s /bin/bash -G docker hugo-portfolio
id hugo-portfolio                 # "docker" doit apparaître
mkdir -p /opt/hugo-portfolio && chown hugo-portfolio:hugo-portfolio /opt/hugo-portfolio
ss -ltn | grep ':8101 '           # rien ne doit s'afficher (port libre)
```

Rien d'autre : pas de clone, pas de `.env` à la main, pas de `docker login`.

### Étape 2 — Clé SSH de déploiement

⚠️ Autorisée **pour `hugo-portfolio` uniquement** (une clé par site : pas celle de `website` / deva2).

En root sur .134 :

```bash
ssh-keygen -t ed25519 -N "" -f /tmp/hugo-portfolio-deploy -C github-actions@sites-infra
install -d -m 700 -o hugo-portfolio -g hugo-portfolio /home/hugo-portfolio/.ssh
echo "restrict $(cat /tmp/hugo-portfolio-deploy.pub)" >> /home/hugo-portfolio/.ssh/authorized_keys
chown hugo-portfolio:hugo-portfolio /home/hugo-portfolio/.ssh/authorized_keys
chmod 600 /home/hugo-portfolio/.ssh/authorized_keys
ssh -i /tmp/hugo-portfolio-deploy -o IdentitiesOnly=yes hugo-portfolio@192.168.11.134 "docker ps > /dev/null && echo OK"
cat /tmp/hugo-portfolio-deploy                      # → secret SSH_KEY (de BEGIN à END inclus)
ssh-keyscan -t ed25519 192.168.11.134 2>/dev/null   # → secret SSH_KNOWN_HOSTS
rm /tmp/hugo-portfolio-deploy /tmp/hugo-portfolio-deploy.pub
```

### Étape 3 — Jetons GitHub

| Jeton | Où le créer | Droits | Sert à |
|---|---|---|---|
| GHCR | Settings → Developer settings → Tokens (**classic**) | `read:packages` uniquement | télécharger l'image privée sur .134 |
| Déclenchement | Settings → Developer settings → **Fine-grained** tokens | repo `sites-infra` seulement, **Contents : Read and write** | permettre au portfolio de lancer le déploiement |

### Étape 4 — Secrets GitHub

**Repo sites-infra → Settings → Secrets and variables → Actions** :

| Secret | Valeur |
|---|---|
| `VPN_SERVER`, `VPN_USER`, `VPN_PASSWORD` | VPN IKEv2 de la Freebox (comme deva2 et ICE) |
| `SSH_HOST` | `192.168.11.134` |
| `SSH_USER` | `hugo-portfolio` |
| `SSH_KEY` | clé **privée** de l'étape 2 |
| `SSH_KNOWN_HOSTS` | ligne `192.168.11.134 ssh-ed25519 …` de l'étape 2 |
| `GHCR_TOKEN` | jeton classic `read:packages` |
| `ENV_CRUSHBRITO`, `ENV_PIZZAMAMA` | 2 lignes chacun, générées par la commande ci-dessous (une fois par secret) |
| `ENV_SUNORCLOUD` | `OWM_API_KEY=…` et `OPENCAGE_API_KEY=…` |

```bash
printf 'DJANGO_SECRET_KEY=%s\nDJANGO_ADMIN_PATH=gestion-%s/\n' "$(openssl rand -base64 48 | tr -d '\n/+=')" "$(openssl rand -hex 4)"
```

L'admin Django est alors à `https://hugomeuriel.fr/projets/<appli>/gestion-xxxx/`.

**Repo hugomeuriel-portfolio → Settings → Secrets → Actions** : `SITES_DEPLOY_TOKEN` = le jeton de
déclenchement.

💡 Ne jamais mettre de vraie valeur dans un fichier d'un repo : uniquement dans les secrets.

### Étape 5 — Reverse proxy Apache sur le serveur main (192.168.11.131)

Copier `apache/hugomeuriel-sites.conf` dans `/etc/apache2/sites-available/hugomeuriel.fr.conf`, puis :

```bash
sudo a2enmod proxy proxy_http headers rewrite
sudo a2ensite hugomeuriel.fr && sudo apache2ctl configtest && sudo systemctl reload apache2
for p in / /projets/natours/ /projets/sunorcloud/ /projets/crushbrito/; do
  curl -s -o /dev/null -w "%{http_code} $p\n" -H "Host: hugomeuriel.fr" http://127.0.0.1$p
done
```

`200` partout (`301` pour crushbrito en HTTP = redirection HTTPS de Django, normal).
⚠️ Ce test se lance **sur .131** : sur .134, `127.0.0.1:80` est un autre serveur web.

DNS : enregistrements A de `hugomeuriel.fr` et `www` → IP publique (celle de deva2.fr). Ne pas toucher à
`photos.hugomeuriel.fr`. Puis :

```bash
sudo certbot --apache -d hugomeuriel.fr -d www.hugomeuriel.fr    # choisir Redirect
```

Pas besoin d'ajouter `X-Forwarded-Proto` à la main dans `-le-ssl.conf` (contrairement à deva2.fr) :
`RequestHeader set X-Forwarded-Proto expr=%{REQUEST_SCHEME}` est recopié par certbot et vaut `https` en 443.

### Étape 6 — Données des applis Django (une fois, juste avant la bascule DNS)

Depuis le PC, VPN actif :

```bash
ssh -t rasp "sudo tar czf /tmp/crushbrito.tgz -C /var/www/crushbrito/osculte db.sqlite3 media && sudo tar czf /tmp/pizzamama.tgz -C /var/www/pizzamama/pizzeria db.sqlite3 media && sudo chmod 644 /tmp/*.tgz"
scp rasp:/tmp/crushbrito.tgz rasp:/tmp/pizzamama.tgz .
scp crushbrito.tgz pizzamama.tgz <admin>@192.168.11.134:/tmp/
ssh -t <admin>@192.168.11.134 "for a in crushbrito pizzamama; do sudo mkdir -p /opt/hugo-portfolio/data/\$a && sudo tar xzf /tmp/\$a.tgz -C /opt/hugo-portfolio/data/\$a && rm /tmp/\$a.tgz; done; sudo chown -R 1000:1000 /opt/hugo-portfolio/data && sudo docker restart hugomeuriel-site-1"
ssh rasp "rm /tmp/crushbrito.tgz /tmp/pizzamama.tgz"
```

### Étape 7 — Premier déploiement et vérification

**sites-infra → Actions → Deploy (VPN) → Run workflow**. Dans le run : `Tunnel VPN établi.`,
`port 22 OUVERT`, puis `200` pour `/` et chacun des 9 projets.

Sur .134 : `docker ps --filter name=hugomeuriel` → **un seul** conteneur `hugomeuriel-site-1`, `Up`.

Puis https://hugomeuriel.fr : cliquer sur chaque projet, se connecter à crushbrito, faire une recherche météo.

### Étape 8 — Nettoyer la Raspberry (quelques jours plus tard)

```bash
ssh -t rasp "sudo rm /etc/nginx/sites-enabled/{portfolio.conf,guessmynumber.conf,icecream.conf,natours.conf,nexter.conf,trillo.conf,robot.hugomeuriel.fr.conf,sunorcloud.hugomeuriel.fr,crushbrito.hugomeuriel.fr.conf,pizzamama.hugomeuriel.fr.conf} && sudo nginx -t && sudo systemctl reload nginx"
ssh -t rasp "sudo systemctl disable --now gunicorn_start_crushbrito gunicorn_start_pizzamama"
ssh -t rasp "sudo rm -rf /var/www/html/admin /var/www/xss"
```

`photos.hugomeuriel.fr.conf` reste actif.

---

## 3. Au quotidien

| Je veux… | Je fais… |
|---|---|
| Modifier le portfolio ou un projet | Modifier `hugomeuriel-portfolio` (racine, `projets/<nom>/` ou `apps/<appli>/`), pousser sur `main` (~4 min). |
| Ajouter un projet statique | Créer `projets/<nom>/`, ajouter son bloc `location` dans `docker/nginx.conf.template` et sa CSP dans `docker/headers/<nom>.conf`, ajouter la carte dans `data.json`, pousser. Rien à changer dans Apache ni sites-infra. |
| Changer une clé ou un secret | Modifier le secret `ENV_…` de sites-infra, puis **Deploy (VPN) → Run workflow**. |
| Revenir à une version précédente | Dans `sites-infra/docker-compose.yml`, `:latest` → `:<sha du commit>`, pousser. Ou `git revert` dans hugomeuriel-portfolio. |
| Voir les logs | Sur .134 : `docker logs -f hugomeuriel-site-1` (Nginx et les deux Django au même endroit). |
| Tester en local | Dans hugomeuriel-portfolio : `docker build -t hugomeuriel .` puis `docker run --rm -p 8080:8080 --tmpfs /tmp hugomeuriel`. |

⚠️ Après une modification d'un workflow, relancer avec **Run workflow**, pas **Re-run jobs**
(un Re-run rejoue l'ancien commit avec l'ancienne version du workflow).

---

## 4. Dépannage

| Erreur | Cause probable | Solution |
|---|---|---|
| `The job was not started because your account is locked due to a billing issue` | Problème de paiement / minutes Actions épuisées sur le compte GitHub | github.com/settings/billing : régler le moyen de paiement ou le plafond, puis relancer. |
| Rouge à « Django security checks » | Config non sûre ou migration manquante | Lire le message ; migration : `python manage.py makemigrations` dans `apps/<appli>/`, commit, push. |
| Rouge à « Smoke test » | Un chemin ne répond pas, un fichier interdit est servi, une CSP manque | Le log liste chaque `ÉCHEC` puis les logs du conteneur. |
| `Secrets manquants : …` | Un secret n'existe pas dans sites-infra | Le créer (nom exact). |
| `VPN refusé : VPN_USER ou VPN_PASSWORD incorrect` | Identifiants VPN faux | Les retaper sans espace ; les tester depuis le PC. |
| `ssh: connect … port 22: Connection timed out` | Le VPN n'est pas monté | Voir les étapes VPN et « Network diagnostics ». |
| `Permission denied (publickey)` | `SSH_KEY` non autorisée pour `hugo-portfolio` | Sur .134 : `journalctl -u ssh -n 20`. |
| `Host key verification failed` | `SSH_KNOWN_HOSTS` faux | Refaire `ssh-keyscan -t ed25519 192.168.11.134`. |
| `unauthorized` au `docker compose pull` | `GHCR_TOKEN` expiré ou sans `read:packages` | Recréer le jeton, mettre à jour le secret. |
| Health check : un chemin ≠ 200 | Le conteneur ou une appli ne démarre pas | Le log affiche les 50 dernières lignes du conteneur. Django : souvent `DJANGO_SECRET_KEY` absente. |
| `403` sur « Trigger deployment » | Jeton de déclenchement sans « Contents: Read and write » | Modifier le jeton. |
| 503 sur hugomeuriel.fr | Apache n'atteint pas .134:8101 | Depuis .131 : `curl -I http://192.168.11.134:8101`. |
| CSRF / « Forbidden » au login Django | `X-Forwarded-Proto` absent | Vérifier `RequestHeader set X-Forwarded-Proto …` dans le vhost 443 (`-le-ssl.conf`). |
| Météo : « Erreur: … » | Clé récente (jusqu'à 2 h d'activation) ou quota | `docker logs hugomeuriel-site-1 2>&1 | grep api/` sur .134. |

---

## 5. Sécurité — rappels

- Aucune vraie valeur dans les fichiers des repos : clés et mots de passe uniquement dans les secrets.
- Les .env du serveur ne sont lisibles que par l'utilisateur du conteneur, montés en lecture seule.
- Conteneur non-root, système de fichiers en lecture seule, aucune capability, `no-new-privileges`,
  limites mémoire/processus ; seul `/data` est modifiable.
- Une CSP par projet, HSTS, limitation de débit sur les connexions Django et l'API météo.
- Le jeton GHCR n'est jamais stocké sur le serveur. Une clé SSH par site.
- Port 8101 publié sur l'IP locale de .134 seulement : pas d'accès depuis Internet sans passer par Apache.
- Historique Git public des anciens repos : les anciennes SECRET_KEY Django et clés météo y sont
  (remplacées), ainsi que les `db.sqlite3` de crushbrito et Pizzeria : passer ces repos en privé ou
  réécrire leur historique.
