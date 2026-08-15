#!/bin/sh
# Run one benchmark's instances with the installed tool, then report back.
#
# Ships the node-side harness (harness.py) and clones the benchmarks repo on the node
# (once — it holds instances.csv + the benchmark data). The harness loops the benchmark's
# instances, running the tool's prepare_instance.sh / run_instance.sh and timing each,
# and writes results_<benchmark_id>.csv, which the step reads back. $BENCHMARKS_DIR
# points the tool at the benchmark data. Node files are keyed by benchmark id because
# benchmark names may contain spaces. The remote script POSTs the log tail to
# ${ROOT_URL}/update/${task_id}/success|failure.
#
# Params (env, from the step handler): benchmark_ip task_id benchmark_id benchmark_name
# version script_dir repository hash. ROOT_URL comes from the backend environment.
# NODE_SSH_KEY locates the node key.
set -eu

ssh_key="${NODE_SSH_KEY:-$HOME/.ssh/comp.pem}"
script_here="$(dirname "$0")"
node="ubuntu@${benchmark_ip}"
ssh_opts="-o StrictHostKeyChecking=accept-new -i ${ssh_key}"
remote_script_path="/home/ubuntu/run_benchmark_${benchmark_id}.sh"
remote_log_path="/home/ubuntu/logs/run_${benchmark_id}.log"

# Ship the node-side harness (lives beside the backend wrappers, one dir up) and the
# shared logging helpers, so the remote banners match every other stage.
ssh $ssh_opts "$node" "mkdir -p /home/ubuntu/logs"
scp $ssh_opts "${script_here}/../harness.py" "${node}:/home/ubuntu/harness.py"
scp $ssh_opts "${COMP_LOG_LIB}" "${node}:/home/ubuntu/comp_log.sh"

ssh $ssh_opts "$node" "cat > ${remote_script_path} <<'REMOTE_SCRIPT'
#!/bin/bash
export COMP_LABEL=\"${COMP_LABEL:-CORA-COMP}\"
. /home/ubuntu/comp_log.sh
cd /home/ubuntu || exit 1
mkdir -p logs
exec > >(tee ${remote_log_path}) 2>&1
# tmux runs this pane in its own session, so this bash leads the process group; record it
# so a per-benchmark abort can SIGTERM the whole run tree (pane + harness) in one shot.
echo \$\$ > /home/ubuntu/run_${benchmark_id}.pgid
log_superstage 'Start — running ${benchmark_name}'

report() {  # success|failure — POST the log tail so the error survives node teardown
    tail -c 200000 ${remote_log_path} > /tmp/run_${benchmark_id}.tail 2>/dev/null || true
    curl --retry 100 --retry-connrefused --max-time 120 --data-binary @/tmp/run_${benchmark_id}.tail ${ROOT_URL}/update/${task_id}/\$1 || true
    return 0
}

# Clone the benchmarks repo once (holds instances.csv + the benchmark data).
if [ ! -d /home/ubuntu/benchmarks_repo/.git ]; then
    rm -rf /home/ubuntu/benchmarks_repo
    log_run 'clone ${repository}' git clone ${repository} /home/ubuntu/benchmarks_repo \
        || { log_superstage 'End — clone FAILED'; report failure; exit 1; }
    if [ -n \"${hash}\" ]; then git -C /home/ubuntu/benchmarks_repo checkout ${hash}; fi
fi

# The harness prints its own per-instance banners; close the stage on its exit status.
# The End superstage carries the instance count (results.csv rows, minus its header),
# so the run needs no separate 'finished' line.
export BENCHMARKS_DIR=/home/ubuntu/benchmarks_repo
results_file=/home/ubuntu/logs/results_${benchmark_id}.csv
if python3 /home/ubuntu/harness.py benchmark \
    /home/ubuntu/benchmarks_repo \"${benchmark_name}\" \
    /home/ubuntu/tool/${script_dir} \
    \${results_file} \
    \"${version}\"; then
    lines=\$(wc -l < \${results_file} 2>/dev/null || echo 1)
    count=\$(( lines > 0 ? lines - 1 : 0 ))
    log_superstage \"End — finished \${count} instance(s); results in \${results_file}\"
    report success
else
    log_superstage 'End — benchmark run FAILED'
    report failure
fi
REMOTE_SCRIPT
chmod +x ${remote_script_path}
tmux kill-session -t run_${benchmark_id} 2>/dev/null
tmux new-session -d -s run_${benchmark_id} /bin/bash ${remote_script_path}"
