ARG BUILD_FROM
FROM ${BUILD_FROM}

WORKDIR /config
CMD cd /config && exec /usr/local/bin/python -m homeassistant --config /config
