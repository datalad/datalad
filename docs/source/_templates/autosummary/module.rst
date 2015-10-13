{{ fullname }}
{{ underline }}

.. automodule:: {{ fullname }}

.. currentmodule:: {{ fullname }}

{% block members %}
{% if name.endswith('api') and members %}
.. autosummary::
   :toctree:
{% for item in members if not item.startswith('_') %}
   {{ item }}
{%- endfor %}

.. toctree::
{%- for item in members if not item.startswith('_') %}
   {{ fullname}}.{{ item }}
{%- endfor %}
{% endif %}

.. autosummary::
{%- for item in members if not item.startswith('_') %}
   {{ fullname }}.{{ item }}
{%- endfor %}

{% endblock %}

{% block functions %}
{% if functions or methods %}
.. rubric:: Functions

.. autosummary::
   :toctree:
{% for item in functions %}
   {{ item }}
{%- endfor %}
{% for item in methods %}
   {{ item }}
{%- endfor %}
{% endif %}
{% endblock %}

{% block classes %}
{% if classes %}
.. rubric:: Classes

.. autosummary::
   :toctree:
{% for item in classes %}
   {{ item }}
{%- endfor %}
{% endif %}
{% endblock %}

{% block exceptions %}
{% if exceptions %}
.. rubric:: Exceptions

.. autosummary::
   :toctree:
{% for item in classes %}
   {{ item }}
{%- endfor %}
{% endif %}
{% endblock %}
