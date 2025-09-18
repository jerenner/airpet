#ifndef ActionInitialization_h
#define ActionInitialization_h 1

#include "G4VUserActionInitialization.hh"

/// Action initialization class.
///
/// This class is instantiated by the G4RunManager and is responsible for
/// building and registering all the user action classes for both the master
/// and worker threads. It ensures that each thread gets its own instance
/// of the necessary action classes.

class ActionInitialization : public G4VUserActionInitialization
{
  public:
    ActionInitialization();
    virtual ~ActionInitialization();

    // This method is called once, on the master thread, before the run starts.
    virtual void BuildForMaster() const override;

    // This method is called for each worker thread.
    virtual void Build() const override;
};

#endif