# sites-infra

Hébergement de hugomeuriel.fr sur le serveur de l'ami (VPN), à la place de la Raspberry.

```
push sur main ─► GitHub Actions (build + contrôles) ─► ghcr.io/hug0003/site-<nom>
                                                              │
   192.168.11.134  (timer toutes les 2 min : docker compose pull + up) ◄─┘
          ▲ ports 8101-8112, joignables seulement depuis l'Apache
Internet ─► 192.168.11.131  Apache : HTTPS, HSTS, un seul domaine
              hugomeuriel.fr/                  → portfolio
              hugomeuriel.fr/projets/<nom>/    → chaque projet
```

Un seul site public : **hugomeuriel.fr**. Les projets ne sont accessibles que sous
`/projets/<nom>/`, via les liens du portfolio. Les anciens sous-domaines redirigent vers ces chemins.

Le serveur va chercher les images lui-même : GitHub ne s'y connecte jamais. Les workflows n'ont donc
ni VPN, ni clé SSH, ni secret.

| Port | Chemin | Repo | Particularité |
|---|---|---|---|
| 8101 | `/` | hugomeuriel-portfolio | |
| 8102 | `/projets/guessmynumber/` | guess-my-number | |
| 8103 | `/projets/icecream/` | glace | |
| 8104 | `/projets/natours/` | travel | |
| 8105 | `/projets/nexter/` | reservation-hotels | |
| 8106 | `/projets/trillo/` | agence-de-voyage | |
| 8107 | `/projets/robot/` | robot | |
| 8108 | `/projets/sunorcloud/` | apiMeteo | clés API dans `env/sunorcloud.env` |
| 8111 | `/projets/crushbrito/` | crushbrito | Django + Nginx, données dans `data/crushbrito` |
| 8112 | `/projets/pizzamama/` | Pizzeria | Django + Nginx, données dans `data/pizzamama` |

Restent sur la Raspberry : photos.hugomeuriel.fr (Immich sur le réseau local), Pi-hole, zabbix.

## Sécurité en place

- **Conteneurs** : Nginx et gunicorn sans root, système de fichiers en lecture seule, aucune capability,
  `no-new-privileges`, limites mémoire/processus, un réseau isolé par appli Django.
- **Ports** : publiés uniquement sur 192.168.11.134 ; à filtrer pour n'accepter que 192.168.11.131.
- **Navigateur** : CSP par site (seuls les domaines réellement utilisés), HSTS, nosniff, X-Frame-Options,
  Referrer-Policy, Permissions-Policy ; SRI sur les scripts et styles des CDN.
- **Fichiers** : dossiers cachés, `.py`, sources Sass, archives et fichiers Docker jamais servis ;
  sites statiques en lecture seule (GET/HEAD).
- **Météo** : les clés d'API restent sur le serveur (Nginx les ajoute) ; 30 requêtes/min par visiteur.
- **Django** : DEBUG désactivé par défaut, SECRET_KEY obligatoire, cookies sécurisés limités à
  `/projets/<appli>`, redirection HTTPS, CSRF sur toutes les suppressions, admin à une adresse secrète,
  connexion limitée à 10 essais/min par visiteur, images envoyées servies sans exécution possible.
- **CI** : `manage.py check --deploy` bloque la publication d'une config Django non sûre ;
  Dependabot propose chaque semaine les mises à jour de sécurité (actions, images, pip).

## 1. Avant tout : révoquer ce qui a fuité sur GitHub

Ces secrets ont été retirés des fichiers, mais **ils restent dans l'historique Git public**.

- **OpenWeatherMap** et **OpenCage** : créer de nouvelles clés, supprimer les anciennes
  (https://home.openweathermap.org/api_keys, https://opencagedata.com/dashboard).
- **SECRET_KEY Django** : ne jamais réutiliser les anciennes ; en générer une par appli (étape 3).
- **Bases SQLite** de crushbrito et Pizzeria : elles contiennent les comptes (mots de passe hachés,
  e-mails, téléphones). Pour les effacer de l'historique : `git filter-repo --path <app>/db.sqlite3 --invert-paths`
  puis `git push --force` (réécrit l'historique, à décider), ou passer ces deux repos en privé.

## 2. Serveur 192.168.11.134

```bash
curl -fsSL https://get.docker.com | sh
sudo useradd -m -s /bin/bash -G docker deploy
sudo mkdir -p /opt/sites && sudo chown deploy:deploy /opt/sites
# copier ce dossier dans /opt/sites (ou git clone si sites-infra devient un repo)
sudo -u deploy chmod +x /opt/sites/update.sh

# Accès aux images GHCR : token GitHub « classic » avec uniquement read:packages
sudo -u deploy docker login ghcr.io -u Hug0003

# Ports des sites : uniquement depuis l'Apache (DOCKER-USER, car Docker passe avant ufw)
sudo iptables -I DOCKER-USER -p tcp -m multiport --dports 8080 ! -s 192.168.11.131 -j DROP
sudo apt install iptables-persistent && sudo netfilter-persistent save

# Mise à jour automatique
sudo cp /opt/sites/systemd/sites-update.* /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now sites-update.timer
```

La règle DOCKER-USER filtre le port **interne** des conteneurs (8080) : tout trafic vers un site
qui ne vient pas de l'Apache est rejeté.

Si l'adresse du serveur n'est pas 192.168.11.134, créer `/opt/sites/.env` avec `HOST_IP=<adresse>`.

Suivi : `journalctl -u sites-update -f`, `docker compose -f /opt/sites/docker-compose.yml ps`.

## 3. Secrets sur le serveur (jamais dans Git)

```bash
cd /opt/sites
cp env/django.env.example env/crushbrito.env      # nouvelle DJANGO_SECRET_KEY + DJANGO_ADMIN_PATH
cp env/django.env.example env/pizzamama.env       # autre clé, autre adresse d'admin
cp env/sunorcloud.env.example env/sunorcloud.env  # nouvelles clés OWM / OpenCage
chmod 600 env/*.env
mkdir -p data/crushbrito/media data/pizzamama/media && sudo chown -R 1000:1000 data
```

## 4. Données de production (crushbrito, pizzamama)

Depuis le PC (VPN actif), juste avant la bascule DNS :

```bash
ssh -t rasp "sudo tar czf /tmp/crushbrito.tgz -C /var/www/crushbrito/osculte db.sqlite3 media && sudo chmod 644 /tmp/crushbrito.tgz"
scp rasp:/tmp/crushbrito.tgz . && scp crushbrito.tgz deploy@192.168.11.134:/opt/sites/data/crushbrito/
ssh deploy@192.168.11.134 "cd /opt/sites/data/crushbrito && tar xzf crushbrito.tgz && rm crushbrito.tgz && sudo chown -R 1000:1000 ."
ssh rasp "rm /tmp/crushbrito.tgz"
```

Pareil pour pizzamama (`/var/www/pizzamama/pizzeria`). Les migrations s'appliquent au démarrage.

## 5. Apache 192.168.11.131

Fichiers du dossier `apache/` :

- `security.conf` : version masquée, TRACE désactivé, TLS 1.2+ ;
- `000-default.conf` : toute requête qui n'est pas pour hugomeuriel.fr reçoit 403 ;
- `hugomeuriel-sites.conf` : le domaine, les chemins `/projets/`, HSTS, redirection des anciens sous-domaines.

Les commandes d'installation sont en tête de `hugomeuriel-sites.conf`. Test depuis le VPN, avant le DNS :

```bash
curl -I -H "Host: hugomeuriel.fr" http://192.168.11.131/projets/natours/
```

## 6. Bascule DNS

1. Enregistrement A de `hugomeuriel.fr` et `www` → IP publique du réseau de l'ami.
2. Dès la propagation : `sudo certbot --apache -d hugomeuriel.fr -d www.hugomeuriel.fr` sur .131.
3. Facultatif : faire pointer aussi les anciens sous-domaines et les ajouter à certbot (redirections).
4. Après quelques jours sans souci, sur la Raspberry : retirer les sites de `/etc/nginx/sites-enabled/`,
   `sudo systemctl disable --now gunicorn_start_crushbrito gunicorn_start_pizzamama`,
   et supprimer `/var/www/html/admin` (copie de l'interface Pi-hole servie publiquement) et `/var/www/xss`.

## Revenir en arrière

Chaque image est aussi taguée avec le SHA du commit : `image: ghcr.io/hug0003/site-<nom>:<sha>`
dans `docker-compose.yml`, puis `./update.sh`.
