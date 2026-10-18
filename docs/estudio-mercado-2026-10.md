# Estudio de mercado en LinkedIn · 18 oct 2026

Búsquedas reales desde la cuenta de Enrique: personas en España (2.º y 3.er grado) cuyo cargo actual contiene
`CEO OR fundador OR fundadora OR propietario OR gerente` y con la palabra clave del sector.

| Sector (palabra clave) | Perfiles | Calidad de la muestra |
| --- | ---: | --- |
| asesoría | 19.500 | Grande pero mezclada (asesores de marketing = competencia) |
| estética | 7.761 | Muy buena: dueñas y gerentes de clínicas de estética |
| academia | 8.392 | Ambigua (también "académico") |
| reformas | 8.202 | Muy buena: dueños y gerentes de empresas de reformas |
| inmobiliaria | 6.946 | Sin muestra; encaja con el ICP |
| coach | 6.291 | Con ruido: entrenadores deportivos y directivos de grandes grupos |
| nutrición | 5.233 | Sin muestra; hay caso real (≈1.500 leads en 3 semanas) |
| dental | 4.091 | Sin muestra |
| catering | 2.761 | Muy buena: CEO y gerentes de caterings; hay caso real (13 ventas) |
| fisioterapia | 2.216 | Sin muestra |

Combinadas: `catering OR eventos OR bodas` 48.434 · `estética OR dental OR fisioterapia OR nutrición` 18.638 ·
`reformas OR interiorismo` 11.985.

Sin filtro de cargo la búsqueda devuelve sobre todo empleados (727.941 en catering/eventos/bodas): el filtro es
imprescindible.

## Conclusión

El mercado no es el límite: con 15 invitaciones al día (≈ 320 al mes) hay años de volumen. El límite es la calidad,
así que se priorizan los sectores donde la muestra encaja y hay caso real:

1. **Catering y eventos**: caso real más fuerte.
2. **Clínicas** (estética, dental, fisio, nutrición): el mayor volumen bien segmentado.
3. **Coaches y formación**: caso real, pero con ruido; la IA descarta lo que no encaja.
4. **Reformas e interiorismo**: muestra muy limpia, venta por presupuesto.
5. **Inmobiliarias**: en borrador, para una segunda fase.

## Límites técnicos de la búsqueda

- Los filtros con varios valores van separados por comas (con `" | "` LinkedIn devuelve 0 sin error).
- El filtro de cargo admite unos 5 términos con OR; con 10 LinkedIn responde 413.
- Las palabras clave admiten 3-4 términos con OR junto con ese filtro de cargo.
