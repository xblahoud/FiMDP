import spot
import buddy

from .consMDP import ConsMDP


class ProductCMDP(ConsMDP):
    """
    CMDP with states that have two components.

    We call the two components `orig_mdp` and `other`, where `orig_mdp` is
    some ConsMDP object and other can be arbitrary domain, for example
    deterministic Büchi automaton, or upper bound of some integer interval.
    The `orig_mdp` and `other` store pointers to the objects of origin for
      the product mdp (if supplied).

    The function `orig_action` maps actions in this object into actions of
    the source ConsMDP object. Similarly,  `other_action` works for the other
    object (if makes sense).
    """

    def __init__(self, orig_mdp, other=None):
        super().__init__()
        self.orig_mdp = orig_mdp
        self.other = other
        self.orig_action_mapping = {}
        self.other_action_mapping = {}
        self.components_to_states_d = {}
        self.components = []

    def add_action(self, src, distribution, label, consumption,
                   orig_action, other_action = None):
        """
        Create a new action in the product using (src, distribution, label,
        consumption) and update mappings to `orig_action` and `other_action`.

        :param src: src in product
        :param distribution: distribution in product
        :param label: label of the action
        :param consumption: consumption in product
        :param orig_action: ActionData object from the original mdp
        :param other_action: Value to be returned by `other_action` for the new
        action.
        :return: action id in the product
        """
        # pa: product action
        pa_id = super().add_action(src, distribution, label, consumption)
        pa = self.actions[pa_id]

        self.orig_action_mapping[pa] = orig_action
        if other_action is not None:
            self.other_action_mapping[pa] = other_action

        return pa_id

    def get_state(self, orig_s, other_s):
        """
        Return state of product based on the two components `(orig_s, other_s)`
        if exists and `None` otherwise.

        :param orig_s: state_id on the original mdp
        :param other_s: state of the other component
        :return: id of state `(orig_s, other_s)` or None
        """
        pair = (orig_s, other_s)
        return self.components_to_states_d.get(pair, None)

    def get_or_create_state(self, orig_s, other_s):
        """
        Return state of product based on the two components `(orig_s, other_s)`
        and create one if it does not exist.

        :param orig_s: state_id on the original mdp
        :param other_s: state of the other component
        :return: id of state `(orig_s, other_s)`
        """
        p_s = self.get_state(orig_s, other_s)
        if p_s is None:
            return self.new_state(orig_s, other_s)

        return p_s

    def new_state(self, orig_s, other_s, reload=False, name=None):
        """
        Create a new product state (orig_s, other_s).

        :param orig_s: state_id in the original mdp
        :param other_s: state of the other component
        :param reload: is state reloading? (Bool)
        :param name: a custom name of the state, `orig_s,other_s` by default.
        :return: id of the new state
        """
        if name is None:
            name = f"{orig_s},{other_s}"
        new_id = super().new_state(reload=reload, name=name)

        pair = (orig_s, other_s)
        self.components_to_states_d[pair] = new_id
        assert len(self.components) == new_id
        self.components.append(pair)

        return new_id

    def orig_action(self, action):
        """
        Decompose the action from the product to the action in the original mdp.

        :param action: ActionData from product (as used in for loops)
        :return: ActionData from the original mdp
        """
        return self.orig_action_mapping.get(action, None)

    def other_action(self, action):
        """
        Decompose the action from the product onto the second component, if
        defined.

        :param action: ActionData from product (as used in for loops)
        :return: value supplied on creation of `action` (if any), or None
        """
        return self.other_action_mapping.get(action, None)


def product_dba(lmdp, aut, init_states=None):
    """Product of a labeled CMDP and a deterministic Büchi automaton.

    Parameters
    ==========
     * lmdp : labeled CMDP (class LCMDP)
     * aut: Spot's object twa_graph representing a deterministic state-based
            Büchi automaton
     * init_states: iterable of ints, the set of initial states of the lcmdp
        The product will be started from these states. If `None`, all states are
        considered initial. At least one state must be declared as initial.

    Returns
    =======
     * (product, targets)
     * product: CMDP object with the product-CMDP
     * targets: target states in the product (accepting states of the Büchi automaton)

    Raise ValueError when empty init supplied
    Raise ValueError if incorrect type of automaton was given
    Raise ValueError if `dba` uses some AP not used by `lcmdp`
    """
    # Check the type of automaton
    if not aut.is_sba():
        raise ValueError("The automaton must be state-based deterministic"
                         "Büchi. You can get one by calling `aut.postprocess("
                         "'BA','complete')`")

    # All states are initial unless specified otherwise
    if init_states is None:
        init_states = range(lmdp.num_states)

    # Check for emptiness of init
    if len(init_states) == 0:
        raise ValueError("The collection of initial states must not be empty")

    # complete DBA if needed
    # TODO: log the changed automaton?
    if not spot.is_complete(aut):
        aut = aut.postprocess("BA", "complete")

    dba = DBAWrapper(aut, lmdp.AP)
    result = ProductCMDP(lmdp, aut)

    # Output states for which we have not yet computed the successors and
    # Büchi states
    todo, targets = [], []

    # Transform a pair of state numbers (mdps, auts) into a state
    # number in the output mdp, creating a new state if needed.
    # Whenever a new state is created, we can add it to todo.
    def get_or_create(mdps, auts):
        p = result.get_state(mdps, auts)
        if p is None:
            p = result.new_state(mdps, auts,
                                 reload=lmdp.is_reload(mdps))
            todo.append(p)
            if aut.state_is_accepting(auts):
                targets.append(p)
        return p

    # Initialization
    # For each state of mdp in init_states, add a new initial state
    aut_i = aut.get_init_state_number()
    for mdp_s in init_states:
        label = lmdp.state_labels[mdp_s]
        aut_s = dba.succ(aut_i, label)
        get_or_create(mdp_s, aut_s)

    # Build all states and edges in the product
    while todo:
        osrc = todo.pop()
        msrc, asrc = result.components[osrc]
        for a in lmdp.actions_for_state(msrc):
            # build new distribution
            odist = {}
            for mdst, prob in a.distr.items():
                label = lmdp.state_labels[mdst]
                aedge = dba.edge(asrc, label)
                adst = aedge.dst
                odst = get_or_create(mdst, adst)
                odist[odst] = prob
            result.add_action(osrc, odist, a.label, a.cons,
                              orig_action=a, other_action=aedge)

    return result, targets


def product_energy(cmdp, capacity, targets=[]):
    """Explicit encoding of energy into state-space

    The state-space of the newly created MDP consists of tuples `(s, e)`,
    where `s` is the state of the input CMDP and `e` is the energy level.
    For a tuple-state `(s,e)` and an action $a$ with consumption (in the
    input CMDP) `c`, all successors of the action `a` in the new MDP are
    of the form `(s', e-c)` for non-reload states and
    `(r, capacity)` for reload states.
    """
    result = ProductCMDP(cmdp, capacity)
    # The list of output states for which we have not yet
    # computed the successors.  Items on this list are triplets
    # of the form `(s, e, p)` where `s` is the state
    # number in the mdp, `e` is the energy level, and p
    # is the state number in the output mdp.
    todo = []
    otargets = []
    sink_created = False

    # Transform a pair of state numbers (s, e) into a state
    # number in the output mdp, creating a new state if needed.
    # Whenever a new state is created, we can add it to todo.
    def dst(s, e):
        p = result.get_state(s, e)
        if p is None:
            p = result.new_state(s, e,
                                 reload=cmdp.is_reload(s))
            if s in targets and e >= 0:
                otargets.append(p)
            todo.append((s, e, p))
        return p

    # Initialization
    # For each state of mdp add a new initial state
    for s in range(cmdp.num_states):
        dst(s, capacity)

    # Build all states and edges in the product
    while todo:
        s, e, p = todo.pop()
        for a in cmdp.actions_for_state(s):
            # negative goes to sink
            if e - a.cons < 0:
                if not sink_created:
                    sink = result.new_state(-1, "-∞", name="sink,-∞")
                    result.add_action(sink, {sink: 1}, "σ", 1, None)
                    sink_created = True
                result.add_action(p, {sink: 1}, a.label, a.cons, a)
                continue
            # build new distribution
            odist = {}
            for succ, prob in a.distr.items():
                new_e = capacity if cmdp.is_reload(succ) else e - a.cons
                out_succ = dst(succ, new_e)
                odist[out_succ] = prob
            result.add_action(p, odist, a.label, a.cons, a)

    return result, otargets


class DBAWrapper:
    """
    Wrapper class around Spot's interface for automaton that answers queries
    for successor in case of deterministic automata.

    AP is a list of names of atomic propositions. The order (and index) of
    the atomic proposition in AP can differ from the order used by the
    automaton. Moreover, the list can contain only a subset of atomic
    propositions of the automaton. It cannot contain superset, as this would
    lead to non-determinism. In queries, atomic propositions should be
    referenced by index in this given list.
    """

    def __init__(self, aut, AP):
        # Check type of automaton
        if not aut.is_deterministic():
            raise ValueError("The automaton is not deterministic.")

        if len(AP) == 0:
            raise ValueError("The list of AP cannot be empty.")

        # Check if all APs of the dba are used by the MDP
        aut_ap = aut.ap()
        for ap in aut_ap:
            if ap not in AP:
                raise ValueError(f"The automaton uses atomic proposition {ap}" +
                                 "not specified in the labeled MDP. Remove it " +
                                 "first! Otherwise, determinism is lost.")

        self.aut = aut
        self.AP = AP

        self.bdd_dict = aut.get_dict()
        self.ap2bdd_var = {}

        # Establish the mapping between AP-indices and BDD variables
        for ap_i, ap in enumerate(AP):
            if ap in aut_ap:
                bddvar_i = aut.get_dict().register_proposition(ap, self)
                self.ap2bdd_var[ap_i] = bddvar_i

    def _bdd_for_label(self, label):
        """Get the BDD for given label (sequence of AP-indices)."""
        cond = buddy.bddtrue
        for ap_i, bdd_var in self.ap2bdd_var.items():
            if ap_i in label:
                cond &= buddy.bdd_ithvar(bdd_var)
            else:
                cond -= buddy.bdd_ithvar(bdd_var)
        return cond

    def __del__(self):
        self.bdd_dict.unregister_all_my_variables(self)
        # Mapping of AP representation in MDP to repr. in automaton

    def edge(self, state, label):
        """
        Get edge from `state` under `label`

        Label is sequence of indices in AP as given by creation of this object.
        """
        for e in self.aut.out(state):
            mdp_bdd = self._bdd_for_label(label)
            if mdp_bdd & e.cond != buddy.bddfalse:
                return e

    def succ(self, state, label):
        """
        Get successor from `state` under `label` given as indices to self.AP.
        """
        return self.edge(state, label).dst

