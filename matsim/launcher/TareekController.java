// SPDX-License-Identifier: GPL-3.0-or-later
//
// Start MATSim 2026.0 for Tareek. Java runs this file directly from source
// (Java 11+ source-file mode), so the repository has no compiled class:
//
//   java -cp <matsim-2026.0.jar>:<lib>/* TareekController.java config.xml
//
// Why: MATSim 2026.0 added a check in GlobalConfigGroup.checkConsistency
// that stops every Tareek run:
//   1. countsScaleFactor must equal flowCapacityFactor. This is a MATSim bug:
//      CountsComparisonAlgorithm multiplies the simulated volume by
//      countsScaleFactor, so the correct value is 1 / flowCapacityFactor.
//      Fixed after the release by MATSim PR #5016 (2026-06-23).
//   2. qsim.storageCapacityFactor must equal qsim.flowCapacityFactor.
// The relative tolerance of the check cannot be set in config.xml in 2026.0
// (MATSim PR #4706 adds the parameter after the release).
//
// This launcher does the PR #5016 counts check itself, then sets the
// tolerance so that the 2026.0 check passes, then runs the normal Controler
// (the same as org.matsim.core.controler.Controler.main). With this, a
// config runs with the same scale factors as in MATSim 2025.0.
// Remove this launcher when Tareek moves to a MATSim release with PR #5016
// and PR #4706 (expected: MATSim 2027.0).

import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.Controler;

public class TareekController {

    public static void main(String[] args) {
        if (args == null || args.length != 1) {
            System.err.println("Usage: TareekController config.xml");
            System.exit(2);
        }
        Config config = ConfigUtils.loadConfig(args[0]);

        double flow = config.qsim().getFlowCapFactor();
        String countsFile = config.counts().getCountsFileName();
        if (countsFile != null && !countsFile.isEmpty()) {
            double scale = config.counts().getCountsScaleFactor();
            double expected = 1.0 / flow;
            if (Math.abs(scale - expected) > 1e-6 * expected) {
                throw new RuntimeException("countsScaleFactor=" + scale + " is not 1/flowCapacityFactor="
                        + expected + " (flowCapacityFactor=" + flow + "). The counts comparison multiplies "
                        + "the simulated volume by countsScaleFactor.");
            }
        }
        System.out.println("TareekController: MATSim 2026.0 scale-factor check replaced by the "
                + "PR #5016 check (flowCapacityFactor=" + flow + ", storageCapacityFactor="
                + config.qsim().getStorageCapFactor() + ", countsScaleFactor="
                + config.counts().getCountsScaleFactor() + ")");
        config.global().setRelativeToleranceForSampleSizeFactors(Double.MAX_VALUE);

        new Controler(config).run();
        System.exit(0);
    }
}
