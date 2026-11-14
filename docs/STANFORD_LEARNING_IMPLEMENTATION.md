# Stanford learning implementation

## Source verification

Ten attached PDFs were opened locally, all 299 pages had text extracted, and
selected mathematical pages were rendered and visually checked. See
LECTURE_INVENTORY.json for source hashes and page counts. Lecture1 (2).pdf is
**not supplied**; Lecture2.pdf is supplied instead. Introductory task/experience/
performance definitions are user-provided context, not verified Lecture1 content.
No claim is made to have studied a missing lecture. Equations partly stored as
vectors/images were checked using rendered pages rather than text extraction.

Pages below are physical PDF pages, counting the first page as 1. Mathematical
notation is re-expressed here; source slides are not redistributed in the repo.

## Implemented and measured

| Concept | Source | Mathematics and code | Tests | Practical use and results | Limits |
|---|---|---|---|---|---|
| Linear regression and squared cost | Lecture2 pp. 4, 6, 34 | h(x)=theta0+theta1*x; J=SSE/(2m); `core.LinearGD`, `loss_gradient` | `test_gradient_finite_difference`, `test_training_checkpoint` | Public regression benchmark; loss 14174.08 to 1446.46 for chosen regularized candidate | Multivariate extension and regularization are additionally informed by library reference |
| Simultaneous gradient descent | Lecture2 pp. 26, 34, 36 | theta := theta-alpha*gradient using one gradient for all parameters | Finite differences and library parity | Training changes numeric weights and lowers objective | Poor learning rates can diverge; no global guarantee for arbitrary future models |
| Mini-batch optimization | Lecture17 pp. 8, 10-11 | Update from shuffled batches; penalty scaled to full-data objective | `test_minibatch` | Reproducible seeded convergence on known linear data | Engineering test is synthetic, not platform evidence |
| Train/validation/test model selection | Lecture10 pp. 9-14 | Fit training only, choose lambda by validation MAE, inspect untouched test after selection | `test_ordered_split`, `test_benchmark` | Public dataset split 265/88/89; selected lambda=10 | Public dataset index order is not chronological event time; TikTok time validation is pending |
| Bias/variance diagnostics and learning curves | Lecture10 pp. 15-17, 23-28 | Training and validation errors at 40/80/160/265 examples | Reproducible `test_benchmark` | `reports/regression_benchmark.json` stores curves | No automatic causal diagnosis from a small curve |
| Feature scaling/mean normalization | Lecture14 p. 15; Lecture12 p. 28 | z=(x-mu_train)/sigma_train; constant columns use scale 1 | `test_train_only_scaling`, `test_constant_feature` | Same preprocessing as reference Ridge | PCA itself not implemented |
| Gaussian anomaly score | Lecture15 pp. 5-9 | log p(x)=-0.5 sum(log(2*pi*variance)+(x-mu)^2/variance) | `test_gaussian` | Numeric log density separates constructed outlier from central sample | No labelled calibration set, false-positive benchmark or operational alerts yet |

The regression checkpoint is safe numeric JSON (`s_ml.linear.v1`). Exact restore
is tested. Checkpointing itself is an engineering extension rather than a claimed
lecture topic. Synthetic tests verify gradients and known solutions; they do not
establish accuracy on real account data. The public real-data regression benchmark
is independently reproducible with `python -m s_ml benchmark`.

## Actual topics extracted, not yet implemented

| Supplied source | Observed topics and examples | Implementation state |
|---|---|---|
| Lecture10 (30 pages) | Housing-price errors, evaluation, model selection, bias/variance, regularization and learning curves | Partial, as above |
| Lecture11 (18 pages) | Spam classifier, error analysis, skewed classes, precision/recall, F1 | Classification/error-category tools pending |
| Lecture12 (31 pages) | SVM objective, margins, Gaussian kernels, feature scaling, model choice | SVM/classification pending |
| Lecture13 (29 pages) | K-means assignments and centroid updates (pp. 15-16), distortion, restarts, K selection | Clustering pending |
| Lecture14 (30 pages) | Compression, visualization, mean normalization, PCA and reconstruction | PCA pending |
| Lecture15 (37 pages) | Gaussian anomaly detection, validation, feature selection, multivariate Gaussian | Diagonal score only; calibrated detection pending |
| Lecture16 (22 pages) | Movie ratings, content-based recommendations, collaborative filtering, factorization, normalization | Recommender training pending; diagnostic rules are not collaborative filtering |
| Lecture17 (24 pages) | Large-data learning, SGD/mini-batch, convergence, online learning, map-reduce | Mini-batch only; online and distributed learning pending |
| Lecture18 (29 pages) | OCR detection/segmentation/classification, sliding windows, data synthesis, ceiling analysis | Architecture reference only; no OCR implementation claimed |
| Lecture2 (49 pages) | Housing-price regression, objective and batch gradient descent | Implemented linear core |

Neural-network source lectures are absent from this supplied set; no neural
network implementation is attributed to them. Unsupervised anomaly scoring is
implemented, but clustering and PCA remain future milestones.

## Outside-course library research

Read official references on 2026-11-14:

- scikit-learn cross-validation: https://scikit-learn.org/stable/modules/cross_validation.html
- scikit-learn TimeSeriesSplit: https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- PyTorch optimization: https://docs.pytorch.org/tutorials/beginner/basics/optimization_tutorial.html

scikit-learn provides the comparator, public dataset and metrics. Its time-series
split preserves order, and comparable fold durations require evenly spaced
samples. TikTok posts are irregular and have delayed labels: future work must
purge immature labels, not blindly apply K-fold or index splitting.

PyTorch's documented zero-gradient/backpropagation/optimizer-step lifecycle is
useful for later neural models. The current implementation uses transparent NumPy
gradients and does not install or benchmark PyTorch. No PyTorch parity is claimed.
L2 implementation is numerically compared against scikit-learn Ridge; the maximum
prediction difference is 0.00412 in the committed public benchmark. Residual
intervals are a labelled heuristic with measured coverage, not calibrated TikTok
confidence or a guaranteed conformal interval.
