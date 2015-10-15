{% if fullname == 'datalad.api' -%}
`{{ name }}`
=={%- for c in name %}={%- endfor %}
.. automodule:: datalad.api

.. currentmodule:: datalad.api

{% for item in members if not item.startswith('_') %}
`{{ item }}`
--{%- for c in item %}-{%- endfor %}

.. autofunction:: {{ item }}
{% endfor %}

{% else -%}
{{ fullname }}
{{ underline }}

.. automodule:: {{ fullname }}
   :members:
   :undoc-members:
   :show-inheritance:
{% endif %}
