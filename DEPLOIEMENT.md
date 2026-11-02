# Déploiement automatique de hugomeuriel.fr

Tuto complet : comment le portfolio et les projets sont déployés, comment tout mettre en place depuis zéro,
et quoi faire quand ça casse. Même principe que deva2.fr (VPN Freebox + SSH vers .134).

---

## 1. Vue d'ensemble

```
git push sur main d'un repo de site (ex. github.com/Hug0003/robot)
  │
  ├─ GitHub Actions du site — deploy.yml :
  │     construit l'image Docker → la publie sur ghcr.io/hug0003/site-<nom> (:latest et :<sha>)
  │     (Django : manage.py check --deploy + contrôle des migrations avant publication)
  │     prévient sites-infra (événement « site-updated », secret SITES_DEPLOY_TOKEN)
  ▼
GitHub Actions de sites-infra — deploy.yml :
  │     connexion au VPN de la Freebox (IKEv2)
  │     SSH hugo-portfolio@192.168.11.134 → copie docker-compose.yml + configs Nginx + écrit les .env
  │     docker compose pull + up -d (seuls les conteneurs dont l'image a changé redémarrent)
  │     vérifie que les 10 sites répondent, sinon le déploiement échoue
  ▼
Visiteur → https://hugomeuriel.fr                 → portfolio
           https://hugomeuriel.fr/projets/<nom>/  → chaque projet
  → serveur main 192.168.11.131 (Apache, reverse proxy + certificat Let's Encrypt)
  → serveur deva2 192.168.11.134:8101-8112 (conteneurs « hugomeuriel-… »)
```

**Un seul site public** : hugomeuriel.fr. Les projets ne sont plus sur des sous-domaines, ils sont
accessibles sous `/projets/<nom>/` via les liens du portfolio. Les anciens sous-domaines peuvent rediriger
vers ces chemins (facultatif).

**Rien n'est cloné sur le serveur** : `/opt/hugo-portfolio` ne contient que ce que le workflow y dépose
et les données des deux applis Django.

### Les repos

| Repo | Chemin | Port .134 | Type |
|---|---|---|---|
| `hugomeuriel-portfolio` | `/` | 8101 | statique |
| `guess-my-number` | `/projets/guessmynumber/` | 8102 | statique |
| `glace` | `/projets/icecream/` | 8103 | statique |
| `travel` | `/projets/natours/` | 8104 | statique |
| `reservation-hotels` | `/projets/nexter/` | 8105 | statique |
| `agence-de-voyage` | `/projets/trillo/` | 8106 | statique |
| `robot` | `/projets/robot/` | 8107 | statique |
| `apiMeteo` | `/projets/sunorcloud/` | 8108 | statique + relais API météo |
| `crushbrito` | `/projets/crushbrito/` | 8111 | Django (+ Nginx) |
| `Pizzeria` | `/projets/pizzamama/` | 8112 | Django (+ Nginx) |
| `sites-infra` (privé) | — | — | compose, Nginx Django, Apache, workflow de déploiement |

### Les fichiers concernés

| Fichier | Rôle |
|---|---|
| `<site>/.github/workflows/deploy.yml` | Build de l'image, contrôles Django, publication GHCR, déclenchement du déploiement. |
| `<site>/Dockerfile` + `docker/` | Image du site : Nginx sans root (statique) ou gunicorn sans root (Django). |
| `sites-infra/.github/workflows/deploy.yml` | VPN → SSH → copie des fichiers → `docker compose up` → vérification. |
| `sites-infra/docker-compose.yml` | Les 12 conteneurs (10 sites + 2 Nginx devant Django), copié sur le serveur à chaque déploiement. |
| `sites-infra/nginx/*.conf` | Nginx devant les applis Django (statiques, médias, limitation des connexions). |
| `sites-infra/apache/hugomeuriel-sites.conf` | Vhost Apache de .131. |
| `sites-infra/env/*.env.example` | Modèles **vides** des fichiers .env. Les vraies valeurs sont uniquement dans les secrets GitHub. |

### Quand est-ce que ça se déclenche ?

| Événement | Image Docker | Déploiement |
|---|---|---|
| Pull request vers main d'un site | construite (+ contrôles Django), pas publiée | — |
| Push / merge sur main d'un site | construite + publiée | ✅ (si `SITES_DEPLOY_TOKEN` est présent) |
| Push sur main de sites-infra | — | ✅ |
| Actions → Deploy (VPN) → Run workflow | — | ✅ |

---

## 2. Mise en place depuis zéro

À faire **une seule fois**. Ensuite, chaque push sur `main` d'un site déploie tout seul.

### Étape 1 — Serveur deva2 (192.168.11.134)

Le déploiement se connecte avec l'utilisateur **`hugo-portfolio`**, et les sites sont installés dans
**`/opt/hugo-portfolio`**.

En root sur .134 :

```bash
docker --version && docker compose version

id hugo-portfolio || useradd -m -s /bin/bash -G docker hugo-portfolio
id hugo-portfolio                 # "docker" doit apparaître

mkdir -p /opt/hugo-portfolio && chown hugo-portfolio:hugo-portfolio /opt/hugo-portfolio

# Ports libres (deva2 utilise 9050…) : rien ne doit s'afficher
ss -ltn | grep -E ':81(0[1-8]|1[12]) '
```

Rien d'autre : pas de clone, pas de `.env` à la main, pas de `docker login` (le workflow s'en charge et
ne laisse aucun jeton sur le serveur).

### Étape 2 — Clé SSH de déploiement

⚠️ La clé est autorisée **pour l'utilisateur `hugo-portfolio`** uniquement (pas la clé de `website` /
deva2 : une clé par site).

En root sur .134 :

```bash
ssh-keygen -t ed25519 -N "" -f /tmp/hugo-portfolio-deploy -C github-actions@sites-infra
install -d -m 700 -o hugo-portfolio -g hugo-portfolio /home/hugo-portfolio/.ssh
echo "restrict $(cat /tmp/hugo-portfolio-deploy.pub)" >> /home/hugo-portfolio/.ssh/authorized_keys
chown hugo-portfolio:hugo-portfolio /home/hugo-portfolio/.ssh/authorized_keys
chmod 600 /home/hugo-portfolio/.ssh/authorized_keys

# Test, comme le fera GitHub : doit afficher OK sans mot de passe
ssh -i /tmp/hugo-portfolio-deploy -o IdentitiesOnly=yes hugo-portfolio@192.168.11.134 "docker ps > /dev/null && echo OK"

cat /tmp/hugo-portfolio-deploy                  # → secret SSH_KEY (de BEGIN à END inclus)
ssh-keyscan -t ed25519 192.168.11.134 2>/dev/null   # → secret SSH_KNOWN_HOSTS
rm /tmp/hugo-portfolio-deploy /tmp/hugo-portfolio-deploy.pub   # une fois les secrets enregistrés
```

`restrict` interdit les tunnels et redirections avec cette clé : elle ne sert qu'à lancer des commandes.

### Étape 3 — Jetons GitHub

| Jeton | Où le créer | Droits | Sert à |
|---|---|---|---|
| GHCR | Settings → Developer settings → Tokens (**classic**) | `read:packages` uniquement | télécharger les images privées sur .134 |
| Déclenchement | Settings → Developer settings → **Fine-grained** tokens | repo `sites-infra` seulement, **Contents : Read and write** | permettre à un site de lancer le déploiement |

### Étape 4 — Secrets GitHub

**Repo sites-infra → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Valeur |
|---|---|
| `VPN_SERVER` | IP publique / domaine de la Freebox (comme deva2 et ICE) |
| `VPN_USER` | utilisateur VPN IKEv2 |
| `VPN_PASSWORD` | mot de passe VPN |
| `SSH_HOST` | `192.168.11.134` |
| `SSH_USER` | `hugo-portfolio` |
| `SSH_KEY` | clé **privée** de l'étape 2 |
| `SSH_KNOWN_HOSTS` | ligne `192.168.11.134 ssh-ed25519 …` de l'étape 2 |
| `GHCR_TOKEN` | jeton classic `read:packages` |
| `ENV_CRUSHBRITO` | voir ci-dessous |
| `ENV_PIZZAMAMA` | voir ci-dessous |
| `ENV_SUNORCLOUD` | voir ci-dessous |

`ENV_CRUSHBRITO` et `ENV_PIZZAMAMA` (une valeur différente pour chacun, générée sur le serveur) :

```bash
printf 'DJANGO_SECRET_KEY=%s\nDJANGO_ADMIN_PATH=gestion-%s/\n' "$(openssl rand -base64 48 | tr -d '\n/+=')" "$(openssl rand -hex 4)"
```

L'admin Django est alors à `https://hugomeuriel.fr/projets/<appli>/gestion-xxxx/`.

`ENV_SUNORCLOUD` :

```
OWM_API_KEY=<clé OpenWeatherMap>
OPENCAGE_API_KEY=<clé OpenCage>
```

**Chacun des 10 repos de site → Settings → Secrets → Actions** : secret `SITES_DEPLOY_TOKEN` = le jeton
de déclenchement. (Compte personnel : pas de secrets partagés entre repos, il faut le mettre 10 fois.)

💡 Ne jamais mettre de vraie valeur dans un fichier du repo (`env/*.example` reste vide) : uniquement
dans les secrets.

### Étape 5 — Reverse proxy Apache sur le serveur main (192.168.11.131)

Prérequis :
- `curl -I http://192.168.11.134:8101` depuis .131 répond (après le premier déploiement).
- Les ports 80 et 443 de la Freebox vont déjà vers .131 (en place pour deva2).

**5.a — HTTP**

Copier `apache/hugomeuriel-sites.conf` dans `/etc/apache2/sites-available/hugomeuriel.fr.conf`, puis :

```bash
sudo a2enmod proxy proxy_http headers rewrite
sudo a2ensite hugomeuriel.fr
sudo apache2ctl configtest          # "Syntax OK"
sudo systemctl reload apache2

# Test sans DNS : 200 partout (301 pour crushbrito/pizzamama = redirection HTTPS de Django, normal)
for p in / /projets/natours/ /projets/robot/ /projets/sunorcloud/ /projets/crushbrito/ /projets/pizzamama/; do
  curl -s -o /dev/null -w "%{http_code} $p\n" -H "Host: hugomeuriel.fr" http://127.0.0.1$p
done
```

⚠️ Ce test se lance **sur .131**. Sur .134, `127.0.0.1:80` est un autre serveur web : le résultat n'a
rien à voir.

**5.b — DNS**

Chez le registrar : enregistrements A de `hugomeuriel.fr` et `www.hugomeuriel.fr` → **IP publique**
(la même que deva2.fr : `dig +short deva2.fr`). Ne pas toucher à `photos.hugomeuriel.fr` (Immich,
reste sur la Raspberry).

**5.c — HTTPS**

Une fois le DNS propagé (`dig +short hugomeuriel.fr`) :

```bash
sudo certbot --apache -d hugomeuriel.fr -d www.hugomeuriel.fr
```

Choisir **Redirect**. Contrairement à deva2.fr, **pas besoin** d'ajouter `X-Forwarded-Proto` à la main
dans `-le-ssl.conf` : le vhost contient `RequestHeader set X-Forwarded-Proto expr=%{REQUEST_SCHEME}`,
que certbot recopie et qui vaut automatiquement `https` sur le port 443.

```bash
curl -I http://hugomeuriel.fr                         # 301 → https://hugomeuriel.fr/
curl -I https://hugomeuriel.fr                        # 200
curl -I https://hugomeuriel.fr/projets/crushbrito/    # 200
sudo certbot renew --dry-run
```

Facultatif : faire pointer aussi les anciens sous-domaines (natours.hugomeuriel.fr…) vers l'IP publique
et les ajouter à certbot : ils redirigent vers `/projets/<nom>/`.

### Étape 6 — Données des applis Django (une fois, juste avant la bascule DNS)

Depuis le PC, VPN actif :

```bash
ssh -t rasp "sudo tar czf /tmp/crushbrito.tgz -C /var/www/crushbrito/osculte db.sqlite3 media && sudo tar czf /tmp/pizzamama.tgz -C /var/www/pizzamama/pizzeria db.sqlite3 media && sudo chmod 644 /tmp/*.tgz"
scp rasp:/tmp/crushbrito.tgz rasp:/tmp/pizzamama.tgz .
scp crushbrito.tgz pizzamama.tgz <admin>@192.168.11.134:/tmp/
ssh -t <admin>@192.168.11.134 "for a in crushbrito pizzamama; do sudo tar xzf /tmp/\$a.tgz -C /opt/hugo-portfolio/data/\$a && rm /tmp/\$a.tgz; done; sudo chown -R 1000:1000 /opt/hugo-portfolio/data && sudo docker restart hugomeuriel-crushbrito-1 hugomeuriel-pizzamama-1"
ssh rasp "rm /tmp/crushbrito.tgz /tmp/pizzamama.tgz"
```

### Étape 7 — Premier déploiement

**sites-infra → Actions → Deploy (VPN) → Run workflow** (branche `main`). Les étapes doivent être vertes,
avec dans l'ordre : `Tunnel VPN établi.`, `port 22 OUVERT`, puis `port 81xx : 200` pour les 10 sites.

### Étape 8 — Vérifier

Sur .134 :

```bash
docker compose -f /opt/hugo-portfolio/docker-compose.yml ps    # 12 conteneurs "running"
```

Puis ouvrir https://hugomeuriel.fr, cliquer sur chaque projet, se connecter à crushbrito, faire une
recherche météo.

### Étape 9 — Nettoyer la Raspberry (quelques jours plus tard)

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
| Mettre en ligne une modif d'un site | Pousser / merger sur `main` du repo du site. C'est tout (~3 min). |
| Changer une clé ou un secret (.env) | Modifier le secret `ENV_…` de sites-infra, puis **Actions → Deploy (VPN) → Run workflow**. Les .env du serveur sont réécrits à chaque déploiement. |
| Changer un port, une config Nginx Django | Modifier sites-infra et pousser sur `main` (redéploie). |
| Revenir à une version précédente d'un site | Dans `sites-infra/docker-compose.yml`, remplacer `:latest` par `:<sha du commit>` pour ce site, pousser. Ou `git revert` dans le repo du site. |
| Voir les logs | Sur .134 : `cd /opt/hugo-portfolio && docker compose logs -f <service>` (ex. `crushbrito`, `sunorcloud`). |
| Ajouter un nouveau projet | Copier `templates/` dans son repo (Dockerfile, docker/, workflow), choisir un port libre, l'ajouter à `docker-compose.yml` et au vhost Apache, ajouter `SITES_DEPLOY_TOKEN` au repo. |
| Lancer un site Django en local | `DJANGO_DEBUG=1 python manage.py runserver` (sans `DJANGO_DEBUG=1`, l'appli exige une vraie SECRET_KEY). |

⚠️ Pour relancer après un changement du workflow, utiliser **Run workflow**, pas **Re-run jobs** :
un Re-run rejoue l'ancien commit avec l'ancienne version du workflow.

---

## 4. Dépannage

Le run en échec dans **Actions** indique l'étape fautive.

| Erreur | Cause probable | Solution |
|---|---|---|
| `Secrets manquants : …` | Un secret n'existe pas dans sites-infra | Le créer (nom exact). |
| `VPN refusé : VPN_USER ou VPN_PASSWORD incorrect` (`ERROR_AUTHENTICATION_FAILURE`) | Identifiants VPN faux | Les retaper sans espace avant/après ; les tester depuis le PC. |
| `ssh: connect to host *** port 22: Connection timed out` | Le VPN n'est pas monté (voir étape « Network diagnostics ») | Si `port 22 INJOIGNABLE` : regarder l'étape VPN au-dessus. |
| `Permission denied (publickey)` | `SSH_KEY` n'est pas autorisée pour `hugo-portfolio` | Sur .134 : `ssh-keygen -lf /home/hugo-portfolio/.ssh/authorized_keys` ; `journalctl -u ssh -n 20` donne la raison exacte. |
| `Host key verification failed` | `SSH_KNOWN_HOSTS` faux ou serveur réinstallé | Refaire `ssh-keyscan -t ed25519 192.168.11.134`. |
| `permission denied … docker.sock` | `hugo-portfolio` pas dans le groupe docker | `usermod -aG docker hugo-portfolio` |
| `unauthorized` / `denied` au `docker compose pull` | `GHCR_TOKEN` expiré ou sans `read:packages` | Recréer le jeton classic, mettre à jour le secret. |
| `port 81xx : 000` ou `502` dans Health check | Le conteneur ne démarre pas | Sur .134 : `docker compose -f /opt/hugo-portfolio/docker-compose.yml logs --tail 50 <service>`. Django : souvent `DJANGO_SECRET_KEY` absente dans `ENV_…`. |
| Build d'un site Django rouge à « Django security checks » | Config non sûre ou migration manquante | Lire le message ; pour une migration : `python manage.py makemigrations`, commit, push. |
| `Secret SITES_DEPLOY_TOKEN absent : image publiée mais pas déployée` | Jeton absent dans ce repo de site | L'ajouter ; en attendant, Run workflow dans sites-infra. |
| 503 sur hugomeuriel.fr | Apache n'atteint pas .134 | Depuis .131 : `curl -I http://192.168.11.134:8101`. |
| 404 sur un projet, CSS cassé | Lien sans `/` final (`/projets/natours`) | Apache redirige vers `/projets/natours/` ; vérifier que le vhost est le bon. |
| CSRF / « Forbidden » au login Django | En-tête `X-Forwarded-Proto` absent | Vérifier que `RequestHeader set X-Forwarded-Proto …` est dans le vhost **443** (`-le-ssl.conf`). |
| Météo : « Erreur: … » | Clé OpenWeather récente (jusqu'à 2 h d'activation) ou quota | `docker compose logs sunorcloud` sur .134. |

---

## 5. Sécurité — rappels

- Aucune vraie valeur dans les fichiers du repo : clés, mots de passe et .env uniquement dans les secrets.
- Les .env du serveur sont écrits avec des droits `600` (lisibles par `hugo-portfolio` seul).
- Conteneurs non-root, système de fichiers en lecture seule, aucune capability, `no-new-privileges`,
  limites mémoire ; un réseau isolé par appli Django.
- Le jeton GHCR n'est jamais stocké sur le serveur (dossier temporaire le temps du pull).
- Une clé SSH par site : la clé de `hugo-portfolio` ne donne pas accès à `website` (deva2) ni à ICE.
- Ports 8101-8112 publiés sur l'IP locale de .134 seulement : pas d'accès depuis Internet sans passer
  par Apache.
- Historique Git public : les anciennes SECRET_KEY Django et les anciennes clés météo sont publiques
  (révoquées / remplacées). Les `db.sqlite3` de crushbrito et Pizzeria y sont aussi : passer ces repos
  en privé ou réécrire leur historique.
