# Copyright 2021 Google LLC.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for optimize_media."""
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
import jax.numpy as jnp
import numpy as np

from lightweight_mmm import lightweight_mmm
from lightweight_mmm import optimize_media
from lightweight_mmm import preprocessing


class OptimizeMediaTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.mock_minimize = self.enter_context(
        mock.patch.object(optimize_media.optimize, "minimize", autospec=True))

  def test_objective_function_generates_correct_value_type_and_sign(self):
    media_shape = (30, 3)
    media = jnp.ones(media_shape, dtype=jnp.float32)
    extra_features = jnp.ones(media_shape)
    target = jnp.ones(30)
    mmm = lightweight_mmm.LightweightMMM()
    mmm.fit(
        media=media,
        extra_features=extra_features,
        target=target,
        costs=jnp.ones(3),
        number_warmup=50,
        number_samples=50,
        number_chains=1)

    kpi_predicted = optimize_media._objective_function(
        extra_features=extra_features,
        media_mix_model=mmm,
        model_input_shape=media_shape,
        media_gap=None,
        target_scaler=None,
        media_scaler=preprocessing.CustomScaler(),
        media_values=jnp.ones(3) * 10)

    self.assertIsInstance(kpi_predicted, jnp.DeviceArray)
    self.assertLessEqual(kpi_predicted, 0)
    self.assertEqual(kpi_predicted.shape, ())

  @parameterized.named_parameters([
      dict(
          testcase_name="zero_output",
          media=np.ones(9),
          prices=np.array([1, 2, 3]),
          budget=18,
          expected_value=0),
      dict(
          testcase_name="negative_output",
          media=np.ones(9),
          prices=np.array([1, 2, 3]),
          budget=20,
          expected_value=-2),
      dict(
          testcase_name="positive_output",
          media=np.ones(9),
          prices=np.array([1, 2, 3]),
          budget=16,
          expected_value=2),
      dict(
          testcase_name="bigger_array",
          media=np.ones(18),
          prices=np.array([2, 2, 2]),
          budget=36,
          expected_value=0),
  ])
  def test_budget_constraint(self, media, prices, budget, expected_value):
    generated_value = optimize_media._budget_constraint(
        media=media, prices=prices, budget=budget)

    self.assertEqual(generated_value, expected_value)

  @parameterized.named_parameters([
      dict(
          testcase_name="media_scaler",
          media_scaler=preprocessing.CustomScaler(),
          expected_media_scaler=preprocessing.CustomScaler()),
      dict(
          testcase_name="without_media_scaler",
          media_scaler=None,
          expected_media_scaler=preprocessing.CustomScaler()),
  ])
  def test_find_optimal_budgets_optimize_called_with_right_params(
      self, media_scaler, expected_media_scaler):

    media_shape = (30, 3)
    media = jnp.ones(media_shape, dtype=jnp.float64)
    if media_scaler:
      media = media_scaler.fit_transform(media)
    extra_features = jnp.ones(media_shape)
    target = jnp.ones(30)
    mmm = lightweight_mmm.LightweightMMM()
    mmm.fit(
        media=media,
        extra_features=extra_features,
        target=target,
        costs=jnp.ones(3),
        number_warmup=50,
        number_samples=50,
        number_chains=1)

    optimize_media.find_optimal_budgets(
        n_time_periods=15,
        media_mix_model=mmm,
        budget=30,
        prices=jnp.ones(3),
        target_scaler=None,
        media_scaler=None)

    _, call_kwargs = self.mock_minimize.call_args_list[0]
    # 15 weeks at 1.2 gives us 18. bounds
    self.assertEqual(call_kwargs["bounds"], [(0.0, 18.0), (0.0, 18.0),
                                             (0.0, 18.0)])
    # Starting values are set at midpoint between lower and upper bound.
    # Therefore 0 and 18 gives us 9.
    np.testing.assert_array_almost_equal(call_kwargs["x0"],
                                         jnp.array([9., 9., 9.]))
    np.testing.assert_array_equal(call_kwargs["fun"].args[5].divide_by,
                                  expected_media_scaler.divide_by)
    np.testing.assert_array_equal(call_kwargs["fun"].args[5].multiply_by,
                                  expected_media_scaler.multiply_by)


if __name__ == "__main__":
  absltest.main()