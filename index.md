---
title: afung docs
---

# afung docs

Engineering reports and specs, newest first.

{% assign docs = site.pages | sort: "name" | reverse %}
{% assign month = "" %}
{% for p in docs %}
  {% assign d = p.name | slice: 0, 8 %}
  {% assign n = d | plus: 0 %}
  {% if n < 19000101 %}{% continue %}{% endif %}
  {% assign m = d | slice: 0, 6 %}
  {% if m != month %}
    {% unless month == "" %}</ul>{% endunless %}
    {% assign month = m %}
    {% capture month_date %}{{ d | slice: 0, 4 }}-{{ d | slice: 4, 2 }}-01{% endcapture %}
<h2>{{ month_date | date: "%B %Y" }}</h2>
<ul>
  {% endif %}
  {% assign ext = p.name | split: "." | last %}
  <li>
    <code>{{ d | slice: 0, 4 }}-{{ d | slice: 4, 2 }}-{{ d | slice: 6, 2 }}</code>
    <a href="{{ p.url | relative_url }}">{{ p.title | default: p.name }}</a>
    <small>{% if ext == "html" %}report{% else %}doc{% endif %}</small>
    {% if p.description %}<br><small>{{ p.description }}</small>{% endif %}
  </li>
{% endfor %}
{% unless month == "" %}</ul>{% endunless %}

{% assign untitled = site.static_files | where: "extname", ".html" | sort: "name" | reverse %}
{% if untitled.size > 0 %}
<h2>Other reports</h2>
<ul>
{% for f in untitled %}
  <li><a href="{{ f.path | relative_url }}">{{ f.basename | slice: 9, 200 | replace: "-", " " | replace: "_", " " | default: f.name }}</a> <small>{{ f.name | slice: 0, 8 }}</small></li>
{% endfor %}
</ul>
{% endif %}
