# emacs: -*- mode: python; py-indent-offset: 4; tab-width: 4; indent-tabs-mode: nil -*-
# ex: set sts=4 ts=4 sw=4 noet:
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
#
#   See COPYING file distributed along with the datalad package for the
#   copyright and license terms.
#
# ## ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ### ##
""" utility classes for repositories

"""

import logging

from.exceptions import InvalidInstanceRequestError

lgr = logging.getLogger('datalad.repo')


class Flyweight(type):
    """Metaclass providing an implementation of the flyweight pattern.

    Since the flyweight is very similar to a singleton, we occasionally use this
    term to make clear there's only one instance (at a time).
    This integrates the "factory" into the actual classes, which need
    to have a class attribute `_unique_instances` (WeakValueDictionary).
    By providing an implementation of __call__, you don't need to call a
    factory's get_xy_repo() method to get a singleton. Instead this is called
    when you simply instantiate via MyClass(). So, you basically don't even need
    to know there were singletons. Therefore it is also less likely to sabotage
    the concept by not being aware of how to get an appropriate object.

    Multiple instances, pointing to the same physical repository can cause a
    lot of trouble. This is why this class exists. You should be very aware of
    the implications, if you want to circumvent that mechanism.

    To use this pattern, you need to add this class as a metaclass to the class
    you want to use it with. Additionally there needs to be a class attribute
    `_unique_instances`, which should be a `WeakValueDictionary`. Furthermore
    implement `_flyweight_id_from_args` method to determine, what should be the
    identifying criteria to consider two requested instances the same.

    Example:

    from weakref import WeakValueDictionary
    from six import add_metaclass

    @add_metaclass(Flyweight)
    class MyFlyweightClass(object):

        _unique_instances = WeakValueDictionary()

        @classmethod
        def _flyweight_id_from_args(cls, *args, **kwargs):

            id = kwargs.pop('id')
            return id, args, kwargs

        def __init__(self, some, someother=None):
            pass

    a = MyFlyweightClass('bla', id=1)
    b = MyFlyweightClass('blubb', id=1)
    assert a is b
    c = MyFlyweightClass('whatever', id=2)
    assert c is not a
    """

    def _flyweight_id_from_args(cls, *args, **kwargs):
        """create an ID from arguments passed to `__call__`

        Subclasses need to implement this method. The ID it returns is used to
        determine whether or not there already is an instance of that kind and
        as key in the `_unique_instances` dictionary.

        Besides the ID this should return args and kwargs, which can be modified
        herein and will be passed on to the constructor of a requested instance.

        Parameters
        ----------
        args:
         positional arguments passed to __call__
        kwargs:
         keyword arguments passed to __call__

        Returns
        -------
        hashable, args, kwargs
          id, optionally manipulated args and kwargs to be passed to __init__
        """
        pass

    def _flyweight_invalid(cls, id):
        """determines whether or not an instance with `id` became invalid and
        therefore has to be instantiated again.

        Subclasses can implement this method to provide an additional condition
        on when to create a new instance besides there is none yet.

        Parameter
        ---------
        id: hashable
          ID of the requested instance

        Returns
        -------
        bool
          whether to consider an existing instance with that ID invalid and
          therefore create a new instance. Default implementation always returns
          False.
        """
        return False

    def _flyweight_reject(cls, id, *args, **kwargs):
        """decides whether to reject a request for an instance

        This gives the opportunity to detect a conflict of an instance request
        with an already existing instance, that is not invalidated by
        `_flyweight_invalid`. In case the return value is not `None`, it will be
        used as the message for an `InvalidInstanceRequestError`,
        raised by `__call__`

        Parameters
        ----------
        id: hashable
          the ID of the instance in question as calculated by
          `_flyweight_id_from_args`
        args:
        kwargs:
          (keyword) arguments to the original call

        Returns:
        --------
        None or str
        """
        return None

    def __call__(cls, *args, **kwargs):

        id_, new_args, new_kwargs = cls._flyweight_id_from_args(*args, **kwargs)
        instance = cls._unique_instances.get(id_, None)

        if instance is None or cls._flyweight_invalid(id_):
            # we have no such instance yet or the existing one is invalidated,
            # so we instantiate:
            instance = type.__call__(cls, *new_args, **new_kwargs)
            cls._unique_instances[id_] = instance
        else:
            # we have an instance already that is not invalid itself; check
            # whether there is a conflict, otherwise return existing one:
            # TODO
            # Note, that this might (and probably should) go away, when we
            # decide how to deal with currently possible invalid constructor
            # calls for the repo classes. In particular this is about calling
            # it with different options than before, that might lead to
            # fundamental changes in the repository (like annex repo version
            # change or re-init of git)

            # force? may not mean the same thing
            msg = cls._flyweight_reject(id_, *new_args, **new_kwargs)
            if msg is not None:
                raise InvalidInstanceRequestError(id_, msg)

        return instance


# TODO: see issue #1100
class RepoInterface(object):
    """common operations for annex and plain git repositories

    Especially provides "annex operations" on plain git repos, that just do
    (or return) the "right thing"
    """

    # Note: Didn't find a way yet, to force GitRepo as well as AnnexRepo to
    # implement a method defined herein, since AnnexRepo inherits from GitRepo.
    # Would be much nicer, but still - I'd prefer to have a central place for
    # these anyway.

    # Note 2: Seems possible. There is MRO magic:
    # http://pybites.blogspot.de/2009/01/mro-magic.html
    # http://stackoverflow.com/questions/20822850/change-python-mro-at-runtime

    # Test!

    def sth_like_file_has_content(self):
        raise NotImplementedError # the real thing in case of annex and True in case of git

