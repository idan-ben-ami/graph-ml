import random

from torch.autograd import Variable

from common import model_meter
from common.firms_conf import general_conf
from common.firms_model_runner import get_features, get_loggers
from common.firms_model_runner import init_seed, ModelRunner, parse_args
from common.firms_model_runner import get_path_info, finished_path


IS_DEBUG = False
# =============================================================================
# ================================== Phase 1 ==================================
# =============================================================================


class PhaseOneRunner(ModelRunner):
    def run(self, conf, run_label):
        features_meta = get_features(conf["feat_type"],
                                     is_directed=self.loaders.is_graph_directed)
        self.loaders.split_train(conf["train_p"], features_meta)

        for loader in self.loaders:
            self._run_year(loader, conf, run_label)

        self._logger.dump_location()
        self._data_logger.dump_location()

    def _run_year(self, loader, conf, run_label):
        self._reset_saved_models()
        models = {name: self._get_gcn_model(name, conf, last_layer=True)
                  for name in ["combined", "multi"]}

        models = {name: {"model": args[0], "opt": args[1], "args": args[2]}
                  for name, args in models.items()}

        labels = Variable(loader.labels).cuda(self._cuda_dev)
        for meta in models.values():
            meta["model"].cuda(self._cuda_dev)
            meta["labels"] = labels.clone()
            meta["args"] = [Variable(getattr(loader, arg)).cuda(self._cuda_dev)
                            for arg in meta["args"]]

        # Train model
        meters = {name: model_meter.ModelMeter(loader.distinct_labels) for name in models}
        train_idx, val_idx = self.loaders.train_idx(), self.loaders.val_idx()
        for epoch in range(conf["epochs"]):
            for name, model_args in models.items():
                indices = self._base_train(epoch, name, model_args, train_idx, val_idx, meters[name])
                self._save_best_model(name, indices, model_args, epoch=epoch)

        # Testing
        test_idx = self.loaders.test_idx()
        for name, model_args in models.items():
            self._load_best_model(name, model_args)
            meter = meters[name]
            meter.clear_diff()
            cur_name = "%s_%s" % (loader.name, name,)
            self._base_test(cur_name, model_args, test_idx, meter)
            self._log_results(meter, conf, name, loader.name)

        return meters


def main(args, paths, label, logger, data_logger):
    seed = random.randint(1, 1000000000)
#    conf = {
#        "kipf": {"hidden": 16, "dropout": 0.5, "lr": 0.01, "weight_decay": 5e-4},
#        "hidden_layers": [16], "multi_hidden_layers": [100, 35], "dropout": 0.6, "lr": 0.01, "weight_decay": 0.001,
#        "norm_adj": True, "feat_type": "combined",
#        "dataset": "firms", "epochs": 200, "cuda": args.cuda, "fastmode": args.fastmode, "seed": seed}
    conf = general_conf
    conf.update({"seed": seed, "cuda": args.cuda, "norm_adj": True, "dataset": "firms", "feat_type": "combined"})
    if IS_DEBUG:
        conf["epochs"] = 2

    init_seed(conf['seed'], conf['cuda'])

    index = 0
    num_iter = 1

    runner = PhaseOneRunner(paths, args.fastmode, conf["norm_adj"], conf["cuda"], conf["is_max"],
                            logger=logger, data_logger=data_logger, is_debug=IS_DEBUG)
    runner.loaders.split_test(conf["test_p"])

    for i in range(num_iter):
        runner.run(conf, str(index + i))
    # results = [runner.run(conf, str(index + i)) for i in range(num_iter)]
    # index += num_iter
    # conf_path = os.path.join(runner.products_path, "t%d_n%d_ft%d.pkl" % (conf["train_p"], norm_adj, ft,))
    # pickle.dump({"res": results, "conf": conf}, open(conf_path, "wb"))

    logger.info("Finished")
    if not IS_DEBUG:
        finished_path(paths["products"])


if __name__ == "__main__":
    inp_args = parse_args()
    path_info = get_path_info("part1", "top")
    logger, data_logger = get_loggers("firms", path_info["products"], is_debug=IS_DEBUG or inp_args.verbose)
    main(inp_args, path_info, "top", logger, data_logger)


# def aggregate_results(res_list, logger):
#     aggregated = {}
#     for cur_res in res_list:
#         for name, vals in cur_res.items():
#             if name not in aggregated:
#                 aggregated[name] = {}
#             for key, val in vals.items():
#                 if key not in aggregated[name]:
#                     aggregated[name][key] = []
#                 aggregated[name][key].append(val)
#
#     for name, vals in aggregated.items():
#         val_list = sorted(vals.items(), key=lambda x: x[0], reverse=True)
#         logger.info("*" * 15 + "%s mean: %s", name,
#                     ", ".join("%s=%3.4f" % (key, np.mean(val)) for key, val in val_list))
#         logger.info("*" * 15 + "%s std: %s", name, ", ".join("%s=%3.4f" % (key, np.std(val)) for key, val in val_list))
