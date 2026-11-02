#!/bin/sh
# Lancé toutes les 2 minutes par sites-update.timer.
# Récupère les nouvelles images publiées par GitHub Actions et ne redémarre
# que les conteneurs dont l'image a changé.
set -eu
cd "$(dirname "$0")"

# Si /opt/sites est un clone du repo sites-infra, prend aussi ses changements
# (nouveau site, port…). Un échec réseau ne bloque pas la mise à jour des images.
if [ -d .git ]; then
  git pull --ff-only -q || echo "git pull impossible, on continue avec la version locale"
fi

docker compose pull -q --ignore-pull-failures

# Pendant la migration, certains sites n'ont pas encore d'image sur GHCR :
# on ne lance que ceux dont l'image est présente, pour ne pas bloquer les autres.
# Un service « xxx-web » (Nginx devant Django) attend que « xxx » soit prêt.
has_image() {
  docker image inspect "$(docker compose config --images "$1")" > /dev/null 2>&1
}
ready=""
for s in $(docker compose config --services); do
  case "$s" in
    *-web) has_image "${s%-web}" && ready="$ready $s" ;;
    *)     has_image "$s" && ready="$ready $s" ;;
  esac
done

if [ -n "$ready" ]; then
  # shellcheck disable=SC2086
  docker compose up -d --remove-orphans --quiet-pull $ready
fi
docker image prune -f > /dev/null
