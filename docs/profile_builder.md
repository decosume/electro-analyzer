# Perfil de playlists para distintos negocios

El script `scripts/build_client_profile.py` genera archivos de perfil (`curated_queries`, `rotation_queries`, etc.) a partir de un brief de negocio. Así podemos reutilizar la automatización de `electro playlist` para barbershops, restaurantes, salas de espera, etc.

## Componentes

- `profiles/mood_library.json`: catálogos por "mood" (ej. `restaurant_daytime_brunch`). Cada entrada tiene `query` y `language`.
- `profiles/rotation_library.json`: buckets de rotación (ej. `restaurant_latin_classics`).
- `clients/<cliente>.json`: brief de negocio con bloques horarios, preferencias de idioma y bucket de rotación.
- También puedes definir variantes por día con `weekday_blocks` y `weekday_descriptions`.

## Ejemplo de brief

```json
{
  "playlist_name": "Restaurante Brisas",
  "description": "Ambiente cálido...",
  "language_weights": {"es": 0.6, "en": 0.3, "pt": 0.1},
  "blocks": [
    {"label": "Brunch", "mood": "restaurant_daytime_brunch", "track_count": 30},
    {"label": "Comida", "mood": "restaurant_afternoon_energy", "track_count": 30},
    {"label": "Cena", "mood": "restaurant_evening_lounge", "track_count": 30}
  ],
  "weekday_blocks": {
    "friday": [
      {"label": "Brunch", "mood": "restaurant_daytime_brunch", "track_count": 25},
      {"label": "Comida", "mood": "restaurant_afternoon_energy", "track_count": 35},
      {"label": "Cena", "mood": "restaurant_evening_lounge", "track_count": 35}
    ]
  },
  "weekday_descriptions": {
    "friday": "Viernes con más energía al mediodía y cierre lounge."
  },
  "rotation_bucket": "restaurant_latin_classics",
  "rotation_count": 15
}
```

## Uso

```bash
source .venv/bin/activate
python scripts/build_client_profile.py clients/restaurant_brisas.json --out profiles/restaurant_brisas.json
electro playlist --profile-config profiles/restaurant_brisas.json --max-tracks 90
```

### Regeneración semanal automática

Ejemplo de cron (miércoles 09:00) para el perfil “Restaurante Mexicano”:

```

### Resolviendo IDs (opcional)

Para evitar rate limits en playlists muy largas, resuelve y persiste los Spotify IDs una vez:

```bash
python scripts/resolve_track_ids.py profiles/restaurant_mexicano.json
```

Eso agrega `"id": "spotify:track:..."` a cada entrada, de modo que `electro playlist` ya no necesita llamar al endpoint de búsqueda.
0 9 * * WED cd /Users/macaria/electro-analyzer && \
source .venv/bin/activate && \
python scripts/build_client_profile.py clients/restaurant_mexicano.json --out profiles/restaurant_mexicano.json && \
electro playlist --force --max-tracks 100 --profile-config profiles/restaurant_mexicano.json
```

## Campos soportados

- `playlist_name`, `description`, `public`: se trasladan directamente al perfil final.
- `language_weights`: distribución deseada (por ejemplo 70 % español, 30 % inglés).
- `blocks`: cada bloque indica el `mood` a usar y cuántos temas tomar del catálogo.
- `weekday_blocks`: opcional; redefine los bloques para un día específico (`monday` ... `sunday`).
- `weekday_descriptions`: opcional; cambia la descripción del playlist por día.
- `rotation_bucket` + `rotation_count`: añade un conjunto fijo de canciones (e.g., clásicos latinos).
- `extra_rotation_queries`: lista manual que se agrega al final.
- `target_duration_minutes`: opcional; delimita la duración total de la playlist (e.g., `540` para 9 h).

El perfil generado ahora también incluye:

- `block_config`: preserva la estructura por bloques para aplicar shuffle determinista dentro de cada bloque.
- `weekday_profiles`: overrides listos para usar con `electro playlist --rotation-cadence daily --for-date YYYY-MM-DD`.

Puedes ampliar `profiles/mood_library.json` y `profiles/rotation_library.json` con más moods/buckets según los tipos de clientes que maneje Digital Monk.

### Gym profile
```bash
source .venv/bin/activate
python scripts/build_client_profile.py clients/gym_generic.json --out profiles/gym_generic.json
electro playlist --profile-config profiles/gym_generic.json --max-tracks 120
```


### Gym (12h) profile
```bash
source .venv/bin/activate
python scripts/build_client_profile.py clients/gym_generic.json --out profiles/gym_generic.json
electro playlist --profile-config profiles/gym_generic.json --max-tracks 200
```
