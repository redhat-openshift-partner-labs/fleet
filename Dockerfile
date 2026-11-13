FROM registry.access.redhat.com/ubi9/python-311:latest AS build

ARG PRIVATEBIN_VERSION=v2.2.1
ARG PRIVATEBIN_SHA256=ad83bd5319317aee7c0682e1839da13d0ab7a2494323914103a842899c0ef1ad

COPY pyproject.toml /src/
COPY fleet /src/fleet
RUN pip install --no-cache-dir /src && \
    curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /tmp oc kubectl && \
    KUSTOMIZE_VERSION=$(curl -sL https://api.github.com/repos/kubernetes-sigs/kustomize/releases \
      | python3 -c "import sys,json; tags=[r['tag_name'] for r in json.load(sys.stdin) if r['tag_name'].startswith('kustomize/')]; print(tags[0].split('/')[-1])") && \
    curl -sL "https://github.com/kubernetes-sigs/kustomize/releases/download/kustomize%2F${KUSTOMIZE_VERSION}/kustomize_${KUSTOMIZE_VERSION}_linux_amd64.tar.gz" \
    | tar xz -C /tmp kustomize && \
    VCLUSTER_VERSION=$(curl -sL https://api.github.com/repos/loft-sh/vcluster/releases/latest \
        | python3 -c "import sys,json; print(json.load(sys.stdin)['tag_name'].lstrip('v'))") && \
    curl -sL "https://github.com/loft-sh/vcluster/releases/download/v${VCLUSTER_VERSION}/vcluster-linux-amd64" \
        -o /tmp/vcluster && chmod +x /tmp/vcluster

RUN curl -fsSL "https://github.com/gearnode/privatebin/releases/download/${PRIVATEBIN_VERSION}/privatebin_Linux_x86_64.tar.gz" \
      -o /tmp/privatebin.tar.gz && \
    echo "${PRIVATEBIN_SHA256}  /tmp/privatebin.tar.gz" | sha256sum -c - && \
    tar -xzf /tmp/privatebin.tar.gz -C /tmp privatebin

FROM registry.access.redhat.com/ubi9-minimal:latest

RUN microdnf install -y openssh-clients openssl-libs ca-certificates jq httpd-tools tzdata && microdnf clean all

# qemu-img converts the pod VM disk to raw. It is not in the UBI 9 repositories and
# is installed from CentOS Stream 9 AppStream; its dependencies come from UBI. The
# repo file is removed so that later installs use UBI only. dnf replaces $basearch with
# the architecture of the build platform (x86_64 or aarch64).
ARG CENTOS_KEY_URL=https://www.centos.org/keys/RPM-GPG-KEY-CentOS-Official-SHA256
ARG CENTOS_KEY_SHA256=5af55449d6c9bc594e2e2fb7222374cb25a8ad2d8ea6ce3de894a3201944daa2

RUN curl -fsSL "${CENTOS_KEY_URL}" -o /etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial && \
    echo "${CENTOS_KEY_SHA256}  /etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial" | sha256sum -c - && \
    rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial && \
    printf '%s\n' \
      '[centos-stream-appstream]' \
      'name=CentOS Stream 9 - AppStream' \
      'baseurl=https://mirror.stream.centos.org/9-stream/AppStream/$basearch/os/' \
      'enabled=1' \
      'gpgcheck=1' \
      'gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial' \
      'includepkgs=qemu-img' \
      > /etc/yum.repos.d/centos-stream-appstream.repo && \
    microdnf install -y qemu-img && \
    rm -f /etc/yum.repos.d/centos-stream-appstream.repo && \
    microdnf clean all

COPY --from=build /opt/app-root /opt/app-root
COPY --from=build /usr/bin/python3.11 /usr/bin/python3.11
COPY --from=build /usr/lib64/python3.11 /usr/lib64/python3.11
COPY --from=build /usr/lib/python3.11 /usr/lib/python3.11
COPY --from=build /usr/lib64/libpython3.11.so.1.0 /usr/lib64/libpython3.11.so.1.0
COPY --from=build /tmp/oc /usr/local/bin/oc
COPY --from=build /tmp/kubectl /usr/local/bin/kubectl
COPY --from=build /tmp/kustomize /usr/local/bin/kustomize
COPY --from=build /tmp/vcluster /usr/local/bin/vcluster
COPY --from=build /tmp/privatebin /usr/local/bin/privatebin

RUN ln -s python3.11 /usr/bin/python3 && ln -s python3 /usr/bin/python

RUN mkdir -p /home/fleet && chown 1001:0 /home/fleet

ENV PATH="/opt/app-root/bin:${PATH}" \
    PYTHONPATH="/opt/app-root/lib/python3.11/site-packages" \
    HOME="/home/fleet"

USER 1001
