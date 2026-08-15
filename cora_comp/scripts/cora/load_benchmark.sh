#!/bin/sh
# Clone the central benchmarks repo on the node, then report back.
#
# Clones ${repository} @ ${hash} into /home/ubuntu/benchmarks_repo (kept in sync with
# cora_comp/benchmarks.py CLONE_DIR). The load step then reads its instances.csv back
# over SSH and fans it into benchmarks. The remote script POSTs the log tail to
# ${ROOT_URL}/update/${task_id}/success|failure, so a clone error is captured in the DB
# even after the node is torn down.
#
# Params (env, from the step handler): benchmark_ip task_id repository hash.
# ROOT_URL comes from the backend environment. NODE_SSH_KEY locates the node key.
set -eu

ssh_key="${NODE_SSH_KEY:-$HOME/.ssh/comp.pem}"
node="ubuntu@${benchmark_ip}"
clone_dir="/home/ubuntu/benchmarks_repo"
remote_script_path="/home/ubuntu/load_benchmark_${task_id}.sh"
remote_log_path="/home/ubuntu/logs/load.log"

# Ship the shared logging helpers so the remote banners match every other stage.
ssh -o StrictHostKeyChecking=accept-new -i "${ssh_key}" "$node" "mkdir -p /home/ubuntu/logs"
scp -o StrictHostKeyChecking=accept-new -i "${ssh_key}" "${COMP_LOG_LIB}" "${node}:/home/ubuntu/comp_log.sh"

ssh -o StrictHostKeyChecking=accept-new -i "${ssh_key}" "$node" \
    "cat > ${remote_script_path} <<'REMOTE_SCRIPT'
#!/bin/bash
export COMP_LABEL=\"${COMP_LABEL:-CORA-COMP}\"
. /home/ubuntu/comp_log.sh
cd /home/ubuntu || exit 1
mkdir -p logs
exec > >(tee ${remote_log_path}) 2>&1
log_stage 'Start — loading benchmarks'
set -x

report() {  # success|failure — POST the log tail so the error is captured even after teardown
    tail -c 200000 ${remote_log_path} > /tmp/load_${task_id}.tail 2>/dev/null || true
    curl --retry 100 --retry-connrefused --max-time 120 --data-binary @/tmp/load_${task_id}.tail ${ROOT_URL}/update/${task_id}/\$1 || true
    return 0
}
finish() {  # \$1 = success|failure — close the stage with a banner, then report
    set +x
    if [ \"\$1\" = success ]; then log_stage 'End — benchmarks loaded'; else log_stage 'End — load FAILED'; fi
    report \"\$1\"
}

rm -rf ${clone_dir} \
    && git clone ${repository} ${clone_dir} \
    && if [ -n \"${hash}\" ]; then git -C ${clone_dir} checkout ${hash}; fi \
    && ls ${clone_dir}/instances.csv \
    && finish success \
    || finish failure
REMOTE_SCRIPT
chmod +x ${remote_script_path}
tmux new-session -d -s load /bin/bash ${remote_script_path}"
