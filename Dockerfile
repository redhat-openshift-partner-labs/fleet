FROM registry.access.redhat.com/ubi9/python-311:latest

COPY . /src
RUN pip install /src

# oc CLI installed from OpenShift mirror
USER 0
RUN curl -sL https://mirror.openshift.com/pub/openshift-v4/clients/ocp/stable/openshift-client-linux.tar.gz \
    | tar xz -C /usr/local/bin oc kubectl
USER 1001
