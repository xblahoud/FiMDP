from math import inf
import sys

class minInitCons:
    """Compute function minInitCons for given consMDP `m`.

    minInitCons_m: S -> N ∪ {∞} returns for given `s` the minimum
    amount `s_m` of resource such that there exists a strategy that
    guarantees reachability of some reload state from s consuming
    at most `s_m`.

    Typical use:
    MI = minInitCons(mdp)
    MI.get_values()
    """

    def __init__(self, mdp, cap = inf):
        self.mdp         = mdp
        self.states      = mdp.num_states
        self.values      = None
        self.safe_values = None
        self.cap         = cap

        self.is_reload  = lambda x: self.mdp.is_reload(x)

    def action_value(self, a, values, zero_cond = None):
        if zero_cond is None:
            zero_cond = self.is_reload
        non_reload_succs = [values[succ] for succ in a.distr.keys()
                   if not zero_cond(succ)]
        a_v = 0 if len(non_reload_succs) == 0 else max(non_reload_succs)
        return a_v + a.cons

    def fixpoint(self):
        """Computes the functional F for given capacity.

        The functionals compute for each state `s` the maximum
        energy needed to reach a reload state from `s`.
        """
        # initialization
        values = [inf for s in range(self.states)]
        self.values = values
        action_value = lambda a: self.action_value(a, values)

        # iterate until a fixpoint is reached (at most |S| iterations)
        iterate = True
        while iterate:
            iterate = False

            for s in range(self.states):
                current_v = values[s]
                actions = self.mdp.actions_for_state(s)
                # candidate_v is now the minimum over action values
                candidate_v = min([action_value(a) for a in actions])

                # F is monotonicly decreasing, # check for decrease only
                if candidate_v < current_v and candidate_v <= self.cap:
                    values[s] = candidate_v
                    iterate = True

        self.values = values

    def safe_reloads_fixpoint(self):
        """Iterate on minInitCons and disable reloads with MI > cap

        Basicaly a least fixpoint that starts with minInitCons. If some
        reload has MI > cap, it is converted to ∞, and we no longer treat
        it as a reload state.

        Currently, we perform at most |S| iterations.
        """
        if self.values is None:
            raise RuntimeError("safe_reloads_fixpoint can be called " +
                               "only after minInitCons aka fixpoint " +
                               "was called")

        # Initialization
        values = list(self.values)
        self.safe_values = values
        zero_c = lambda succ: (self.mdp.is_reload(succ) and \
                              values[succ] <= self.cap and \
                              values[succ] != inf)
        action_value = lambda a: self.action_value(a, values, zero_c)

        # iterate until a fixpoint is reached or for at most |S| steps
        iterate = True
        while iterate:
            iterate = False

            for s in range(self.states):
                current_v = values[s]
                if current_v > self.cap or current_v == inf:
                    continue
                actions = self.mdp.actions_for_state(s)
                # candidate_v is now the minimum over action values
                candidate_v = min([action_value(a) for
                                   a in actions])
                candidate_v = inf if candidate_v > self.cap else candidate_v

                # least fixpoint increases only
                if candidate_v > current_v:
                    values[s] = candidate_v
                    iterate = True

    def get_values(self, recompute=False):
        """Return (and compute) minInitCons list for self.m.

        When called for the first time, it computes the values.
        Recomputes the values if requested by `recompute`.
        """
        if self.values is None or recompute:
            self.fixpoint()
        return self.values

    def get_safe_values(self, recompute=False):
        """Return (and compute) safe runs minimal cost for self.capacity

        When called for the first time, it computes the values.
        Recomputes the values if requested by `recompute`.
        """
        if self.safe_values is None or recompute:
            self.get_values()
            self.safe_reloads_fixpoint()
            for s in range(self.states):
                if self.mdp.is_reload(s) and self.safe_values[s] < self.cap:
                    self.safe_values[s] = 0
        return self.safe_values
