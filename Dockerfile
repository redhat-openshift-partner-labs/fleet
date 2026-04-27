FROM registry.access.redhat.com/ubi9/python-311:latest AS build

COPY pyproject.toml /src/
COPY fleet /src/fleet
RUN pip install --no-cache-dir /src && \
    curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /tmp oc kubectl && \
    KUSTOMIZE_VERSION=$(curl -sL https://api.github.com/repos/kubernetes-sigs/kustomize/releases \
      | python3 -c "import sys,json; tags=[r['tag_name'] for r in json.load(sys.stdin) if r['tag_name'].startswith('kustomize/')]; print(tags[0].split('/')[-1])") && \
    curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
    | tar xz -C /tmp kustomize

FROM registry.access.redhat.com/ubi9-minimal:latest

RUN microdnf install -y openssh-clients openssl-libs && microdnf clean all

COPY --from=build /opt/app-root /opt/app-root
COPY --from=build /usr/bin/python3.11 /usr/bin/python3.11
COPY --from=build /usr/lib64/python3.11 /usr/lib64/python3.11
COPY --from=build /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=build /usr/lib64/libpython3.11.so.1.0 /usr/lib64/libpython3.11.so.1.0
COPY --from=build /tmp/oc /usr/local/bin/oc
COPY --from=build /tmp/kubectl /usr/local/bin/kubectl
COPY --from=build /tmp/kustomize /usr/local/bin/kustomize

RUN ln -s python3.11 /usr/bin/python3 && ln -s python3 /usr/bin/python

ENV PATH="/opt/app-root/bin:${PATH}" \
    PYTHONPATH="/opt/app-root/lib/python3.11/site-packages"

USER 1001
