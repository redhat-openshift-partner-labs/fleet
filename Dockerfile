FROM registry.access.redhat.com/ubi9/python-311:latest AS build

COPY pyproject.toml /src/
COPY fleet /src/fleet
RUN pip install --no-cache-dir /src && \
    curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /tmp oc kubectl

FROM registry.access.redhat.com/ubi9-micro:latest

COPY --from=build /opt/app-root /opt/app-root
COPY --from=build /usr/bin/python3.11 /usr/bin/python3.11
COPY --from=build /usr/lib64/python3.11 /usr/lib64/python3.11
COPY --from=build /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=build /usr/lib64/libpython3.11.so.1.0 /usr/lib64/libpython3.11.so.1.0
COPY --from=build /tmp/oc /usr/local/bin/oc
COPY --from=build /tmp/kubectl /usr/local/bin/kubectl

RUN ln -s python3.11 /usr/bin/python3 && ln -s python3 /usr/bin/python

ENV PATH="/opt/app-root/bin:${PATH}" \
    PYTHONPATH="/opt/app-root/lib/python3.11/site-packages"

USER 1001
