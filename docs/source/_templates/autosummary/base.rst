{% if module.endswith('api') -%}
`{{ name }}`
=={%- for c in name %}={%- endfor %}
.. currentmodule:: {{ module }}

.. auto{{ objtype }}:: {{ objname }}
   :annotation:
{%- else %}
{{ fullname }}
{{ underline }}

.. currentmodule:: {{ module }}

.. auto{{ objtype }}:: {{ objname }}
{%- endif %}
