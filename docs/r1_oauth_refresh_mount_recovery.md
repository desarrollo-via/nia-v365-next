# Recuperación de montaje R1

## Alcance local

La publicación de PR 26 entregó salud normal, pero la ruta R1 devolvió 404: la
fábrica existía sin punto de montaje. El helper
`r1_oauth_refresh_internal_mount.py` recibe bindings inyectados y no lee
configuración, secretos ni red. La prueba demuestra la ruta contractual, 401
anónimo y cero llamadas al owner.

## Binding de host

El host sólo consulta cuatro App Settings exactos: issuer, audience, cliente
autorizado y URI JWKS. La URI debe ser la de claves públicas v2 de Entra. No
se enumeran App Settings, no se leen secretos y el owner OAuth queda inyectado
como `unbound`, por lo que este montaje no puede abrir Key Vault ni renovar.
JWKS se obtiene únicamente tras un bearer, nunca en la petición anónima.

## Rollback verificable

Si la publicación o postlectura falla, el rollback se construye como un nuevo
commit de reversión de esta entrega, revisado mediante PR y desplegado por el
workflow normal. Se revierten únicamente las cuatro App Settings allowlisted;
no se usa dispatch por SHA, pues el intento anterior fue rechazado por no
existir ese ref remoto.
